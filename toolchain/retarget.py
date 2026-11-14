"""Retarget a kotlinc-native textual IR module to Cortex-M4 (thumbv7em-none-eabihf).

usage: python retarget.py in.ll out.ll [--no-tls] [--single-core] [--size [--hot REGEX]]
                          [--stubs stubs.c] [--eh-stubs] [--drop-ctors]

- target triple -> thumbv7em-unknown-none-eabihf (the data layout of armv6kz/armv7 Linux EABI and thumbv7em EABI
  is identical: e-m:e-p:32:32-Fi8-i64:64-v128:64:128-a:0:32-n32-S64; checked, not assumed)
- replaces the "target-cpu" / "target-features" function attributes with the ones clang gives C code built for
  paths.target_flags(), so Kotlin and the C runtime carry identical attributes
- --no-tls: single thread, so thread-local storage becomes ordinary storage (no __aeabi_read_tp)
- --single-core: the init-state check before a file's globals becomes a plain load (no DMB, hoistable out of loops)
- --size: minsize/optsize on every Kotlin function; --hot REGEX keeps full speed for the functions whose symbol it
  matches (searched in the symbol as Kotlin/Native writes it, e.g. kfun:pkg#name(kotlin.Int){}kotlin.Int; an error
  when it matches none). The summaries ('N hot functions', 'single-core: N ...') go to stderr.
- --stubs writes a C file defining every external function / global as a trapping stub (for size measurements);
  --eh-stubs adds __cxa_end_cleanup, which the ARM backend emits itself for EHABI cleanups (it is not in the IR)
- --drop-ctors empties @llvm.global_ctors (measures the program without eager module initializers)
- kotlin.random: Random.Default takes its seed from the board hook kmicro_random_seed() instead of the clock
  (runtime/time.c), so Random needs no clock
- String.toDouble()/toFloat(): the hexadecimal parser calls runtime/hexfloat.c instead of compiling regular
  expressions, so number parsing does not link the Regex engine
- the stdlib's Unicode tables stay in flash instead of being copied to the heap on first use
- one of these three rewrites that matches nothing in a module that defines the code it rewrites prints a warning
  (stderr): the sign of the IR of another compiler version
Debug information (kotlinc-native -g) passes through intact: every rewrite keeps or drops whole !dbg attachments.
"""
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import paths  # noqa: E402

EXPECT_DL = 'e-m:e-p:32:32-Fi8-i64:64-v128:64:128-a:0:32-n32-S64'
# thread_local as the keyword of a global's definition: after the name, before the first quote of the line. A string
# literal of -Xbinary=latin1Strings=true is stored as its text and may hold the word.
TLS_RE = re.compile(r'^(@(?:"[^"\n]*"|[\w.$-]+) = [^"\n]*?)\bthread_local(?:\([a-z]+\))? ', re.M)


def target_attributes(cache):
    """The "target-cpu"="..." and "target-features"="..." attributes clang gives a C function compiled with
    paths.target_flags(), read from an empty one. Kept in the file `cache` for that clang (path, size, time) and flags."""
    clang = paths.clang()
    st = clang.stat()
    key = repr((str(clang), st.st_size, st.st_mtime_ns, paths.target_flags()))
    cpu_re, features_re = r'"target-cpu"="[^"]*"', r'"target-features"="[^"]*"'
    try:
        k, cpu, features = cache.read_text(encoding='utf-8').splitlines()
        if k == key and re.fullmatch(cpu_re, cpu) and re.fullmatch(features_re, features):   # not a cut-off write
            return cpu, features
    except (OSError, ValueError):
        pass
    r = subprocess.run([str(clang), *paths.target_flags(), '-S', '-emit-llvm', '-x', 'c', '-', '-o', '-'],
                       input='void f(void) {}\n', capture_output=True, text=True, errors='replace')
    cpu = re.search(cpu_re, r.stdout)
    features = re.search(features_re, r.stdout)
    if r.returncode != 0 or not cpu or not features:
        sys.exit(f'retarget: cannot read the target attributes from {clang}:\n{r.stderr[-2000:]}')
    cache.write_text(f'{key}\n{cpu.group(0)}\n{features.group(0)}\n', encoding='utf-8')
    return cpu.group(0), features.group(0)


def ir_name(name):
    """A symbol as the IR writes it -> as Kotlin/Native spells it: without quotes, \\XX escapes decoded (UTF-8)."""
    if not name.startswith('"'):
        return name
    raw = re.sub(r'\\([0-9A-Fa-f]{2})', lambda m: chr(int(m.group(1), 16)), name[1:-1])
    return raw.encode('latin-1', 'replace').decode('utf-8', 'replace')


def unmatched(text, symbol, effect):
    """A rewrite of the standard library changed nothing. That is right for a module without the code it rewrites.
    When the module defines a function whose symbol matches the regular expression `symbol`, the code is there in a
    form the rewrite does not know, as another compiler version may write it: a warning with what the program then
    does."""
    m = re.search(r'^define [^\n]*@("[^"\n]*(?:' + symbol + r')[^"\n]*")', text, re.M)
    if m:
        print(f'retarget: warning: a rewrite of the standard library matched nothing, although the module defines '
              f'{ir_name(m.group(1))}: {effect}. retarget.py is written for the IR of Kotlin/Native '
              f'{paths.KOTLIN_NATIVE_VERSION}; another version may write this code in another way.', file=sys.stderr)


def replace_body(text, name, params, body, symbol, effect):
    """`text` with the body of the function `name`(`params`) replaced; its define line stays, without a !dbg
    attachment (the new body has no debug locations). Unchanged when there is no such function, with the warning of
    unmatched() when a function like it (`symbol`) is defined."""
    pat = re.compile(r'^(define [^\n]*@"' + re.escape(name) + '"' + re.escape(params) + r'[^\n]*?)(?: !dbg ![0-9]+)? \{$'
                     r'.*?^\}$', re.M | re.S)
    text, n = pat.subn(lambda m: m.group(1) + ' {\n' + body + '}', text, count=1)
    if not n:
        unmatched(text, symbol, effect)
    return text


args = sys.argv[1:]
src, dst = args[0], args[1]
stubs = args[args.index('--stubs') + 1] if '--stubs' in args else None

try:
    text = open(src, encoding='utf-8').read()
except UnicodeDecodeError:              # bitcode, or another binary file
    text = ''
dl = re.search(r'^target datalayout = "([^"]*)"', text, re.M)
if not dl:
    sys.exit(f'retarget: {src} is not textual LLVM IR (no target datalayout)')
dl = dl.group(1)
if dl != EXPECT_DL:
    sys.exit(f'unexpected data layout {dl}')
text = re.sub(r'^target triple = "[^"]*"', f'target triple = "{paths.triple()}"', text, count=1, flags=re.M)
# The exact cpu/feature strings clang gives the C runtime (paths.target_flags()): Kotlin functions and the runtime then
# carry identical attributes, so LTO may inline runtime hooks (UpdateHeapRef, EnterFrame...) into Kotlin code. Any
# difference, from another LLVM version or another CPU, would silently stop that inlining.
M4_CPU, M4_FEATURES = target_attributes(Path(dst).with_name('target_attributes.txt'))
text = re.sub(r'"target-cpu"="[^"]*"', lambda m: M4_CPU, text)
text = re.sub(r'"target-features"="[^"]*"', lambda m: M4_FEATURES, text)
text = re.sub(r'^(attributes #\d+ = )\{ \}$', lambda m: m.group(1) + '{ "kmicro"="retargeted" }', text, flags=re.M)
# Definitions with no attribute group at all (the cinterop bridges and wrappers that bridges.py copies) would carry
# no cpu/features: the inliner then refuses to put a Cortex-M4 callee (hw.c's one-instruction helpers) into them.
NOATTR = re.compile(r'^(define [^\n]*\))((?: !dbg ![0-9]+)?) \{$', re.M)
if NOATTR.search(text):
    text = NOATTR.sub(r'\1 #9999\2 {', text)
    text += f'\nattributes #9999 = {{ nounwind {M4_CPU} {M4_FEATURES} }}\n'
if '--hot' in args and '--size' not in args:
    sys.exit('retarget: --hot only applies with --size')
if '--size' in args:  # optimize for size: LLVM's minsize/optsize on every Kotlin function (= clang -Oz)
    # --hot REGEX: functions whose name matches keep full speed optimisation (their attribute group is cloned
    # without minsize/optsize), e.g. code that runs in a real-time interrupt.
    hot = None
    if '--hot' in args:
        if args.index('--hot') + 1 >= len(args):
            sys.exit('retarget: --hot needs a regular expression')
        hot_src = args[args.index('--hot') + 1]
        try:
            hot = re.compile(hot_src)
        except re.error as e:
            sys.exit(f'retarget: --hot {hot_src!r} is not a valid regular expression: {e}')
    groups = {m.group(1): m.group(2) for m in re.finditer(r'^attributes #(\d+) = \{ (.*) \}$', text, re.M)}
    clones = {}
    if hot:
        def retag(m):
            name, grp = ir_name(m.group(2)), m.group(4)
            if not hot.search(name) or grp not in groups:
                return m.group(0)
            if grp not in clones:
                clones[grp] = str(90000 + len(clones))
            return m.group(1) + m.group(2) + m.group(3) + '#' + clones[grp] + m.group(5)
        # (anything may follow the group: most Kotlin functions carry "personality ptr @__gxx_personality_v0")
        text = re.sub(r'^(define [^@\n]*@)("[^"]+"|[\w.$]+)(\([^\n]*?\) )#(\d+)( [^\n]*\{)$', retag, text, flags=re.M)
    text = re.sub(r'^(attributes #\d+ = \{ )', r'\1minsize optsize ', text, flags=re.M)
    for grp, new_id in clones.items():
        text += f'\nattributes #{new_id} = {{ {groups[grp]} }}\n'
    if hot:
        n_hot = len(re.findall(r'^define [^\n]*#9\d{4} [^\n]*\{$', text, re.M))
        if n_hot == 0:
            sys.exit(f'retarget: --hot {hot_src!r} matches no function (symbols look like '
                     f'kfun:package#function(kotlin.Int){{}}kotlin.Int)')
        print(f'size: minsize everywhere except {n_hot} hot functions', file=sys.stderr)
if '--no-tls' in args:
    text = TLS_RE.sub(r'\1', text)
if '--single-core' in args:
    # Every access to a file's globals first checks its init state with an acquire load (a DMB on the M4, and LLVM
    # may not hoist it out of a loop). kmicro runs Kotlin on one core in one thread, and interrupt handlers never
    # initialise globals (the runtime stops if they try), so a plain load is exact: no barrier, hoistable.
    text, n = re.subn(r'load atomic (i32), ptr (@"state_global\$[^"]*") acquire, align 4', r'load \1, ptr \2, align 4', text)
    print(f'single-core: {n} init-state loads made plain', file=sys.stderr)
if '--drop-ctors' in args:
    text = re.sub(r'^@llvm\.global_ctors = .*$', '', text, count=1, flags=re.M)
# kotlin.random: constructing any Random, Random(42) too, creates Random.Default (NativeRandom), which seeds itself
# from the monotonic clock. Its seed comes from the board hook kmicro_random_seed instead (runtime/time.c), so random
# numbers work on a board without a clock.
CLOCK = '@Kotlin_system_getSteadyTimeNanos('
seeds = []                              # the clock calls replaced, per function of kotlin.random


def seed_from_hook(m):
    seeds.append(m.group(0).count(CLOCK))
    return m.group(0).replace(CLOCK, '@kmicro_random_seed(')


text = re.sub(r'^define [^\n]*@"kfun:kotlin\.random[.#][^\n]*\{$.*?^\}$', seed_from_hook, text, flags=re.M | re.S)
if '@kmicro_random_seed(' in text:
    text += '\ndeclare i64 @kmicro_random_seed()\n'
if not sum(seeds):
    unmatched(text, r'kotlin\.random\.NativeRandom', 'Random.Default may still take its seed from the clock')
# String.toDouble()/toFloat(): FloatingPointParser hands hexadecimal text to HexStringParser. Its companion compiles a
# Regex when it is created, which happens before the hex test, so decimal text pays too (about 19 KB of heap kept),
# and its parse() uses more regular expressions. parseDouble/parseFloat become calls to runtime/hexfloat.c, the same
# algorithm without them, and the companion's initialiser does nothing: a program that does not use Regex itself
# links no Regex engine.
HEX = 'kfun:kotlin.native.internal.HexStringParser.Companion'
REGEX_LINKED = 'String.toDouble() and toFloat() may still link the Regex engine'
text = replace_body(text, HEX + '.<init>#internal', '(ptr %0)', '  ret void\n',
                    r'HexStringParser[^"]*Companion[^"]*<init>', REGEX_LINKED)
text = replace_body(text, HEX + '#parseDouble(kotlin.String){}kotlin.Double', '(ptr %0, ptr %1)',
                    '  %r = call double @kmicro_hex_to_double(ptr %1)\n  ret double %r\n',
                    r'HexStringParser[^"]*parseDouble', REGEX_LINKED)
text = replace_body(text, HEX + '#parseFloat(kotlin.String){}kotlin.Float', '(ptr %0, ptr %1)',
                    '  %r = call float @kmicro_hex_to_float(ptr %1)\n  ret float %r\n',
                    r'HexStringParser[^"]*parseFloat', REGEX_LINKED)
for fn, ty in (('kmicro_hex_to_double', 'double'), ('kmicro_hex_to_float', 'float')):
    if f'@{fn}(' in text:
        text += f'\ndeclare {ty} @{fn}(ptr)\n'
# Unicode tables (Char.category, isLetter, the case mappings...): the initialiser of each generated table file copies
# its tables from their constants into the heap (intArrayOf semantics), from 2.4 KB for an ASCII uppercase() to
# 11.7 KB for Char.category, kept for good. These tables are private to the stdlib and never written, so the constant
# itself is used: a permanent object, which the collector never frees.
COPY = re.compile(r'call ptr @"kfun:kotlin\.collections#copyOf__at__[^"]*"\((ptr @[0-9]+), ptr %[0-9]+\)')
tables = []                             # the copies replaced, per table file


def keep_constant(m):
    body, n = COPY.subn(r'getelementptr inbounds i8, \1, i32 0', m.group(0))
    tables.append(n)
    return body


text = re.sub(r'^define internal void @"kfun:kotlin\.text\.\$init_global\$_\w+\.kt#internal"\(\)[^\n]*\{$.*?^\}$',
              keep_constant, text, flags=re.M | re.S)
if not sum(tables):
    unmatched(text, r'kotlin\.text\.[^"]*init_global\$_', 'the Unicode tables may be copied to the heap on first use')
open(dst, 'w', encoding='utf-8', newline='\n').write(text)

if stubs:
    funcs, globs = set(), set()
    for m in re.finditer(r'^declare\s+[^@]*@("?[^"(\s]+"?)\(', text, re.M):
        n = m.group(1).strip('"')
        if not n.startswith('llvm.'):
            funcs.add(n)
    for m in re.finditer(r'^@("?[^"=\s]+"?)\s*=\s*external\b', text, re.M):
        globs.add(m.group(1).strip('"'))
    if '--eh-stubs' in args:
        funcs.add('__cxa_end_cleanup')
    with open(stubs, 'w', encoding='utf-8', newline='\n') as f:
        f.write('/* generated: trapping stubs for every runtime symbol the Kotlin module needs */\n')
        for n in sorted(funcs):
            f.write(f'__attribute__((noinline)) void {n}(void) {{ __builtin_trap(); }}\n')
        for n in sorted(globs):
            f.write(f'void *{n}[4];\n')
    print(f'{len(funcs)} function stubs, {len(globs)} global stubs')
