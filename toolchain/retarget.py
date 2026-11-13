"""Retarget a kotlinc-native textual IR module to Cortex-M4 (thumbv7em-none-eabihf).

usage: python retarget.py in.ll out.ll [--no-tls] [--single-core] [--size [--hot REGEX]]
                          [--stubs stubs.c] [--eh-stubs] [--drop-ctors]

- target triple -> thumbv7em-unknown-none-eabihf (the data layout of armv6kz/armv7 Linux EABI and thumbv7em EABI
  is identical: e-m:e-p:32:32-Fi8-i64:64-v128:64:128-a:0:32-n32-S64; checked, not assumed)
- strips the "target-cpu" / "target-features" function attributes, so the codegen CPU (-mcpu=cortex-m4) applies
- --no-tls: single thread, so thread-local storage becomes ordinary storage (no __aeabi_read_tp)
- --single-core: the init-state check before a file's globals becomes a plain load (no DMB, hoistable out of loops)
- --size: minsize/optsize on every Kotlin function; --hot REGEX keeps full speed for the symbols it matches
- --stubs writes a C file defining every external function / global as a trapping stub (for size measurements);
  --eh-stubs adds __cxa_end_cleanup, which the ARM backend emits itself for EHABI cleanups (it is not in the IR)
- --drop-ctors empties @llvm.global_ctors (measures the program without eager module initializers)
"""
import re
import sys

EXPECT_DL = 'e-m:e-p:32:32-Fi8-i64:64-v128:64:128-a:0:32-n32-S64'
TLS_RE = re.compile(r'\bthread_local(?:\([a-z]+\))? ')

args = sys.argv[1:]
src, dst = args[0], args[1]
stubs = args[args.index('--stubs') + 1] if '--stubs' in args else None

text = open(src, encoding='utf-8').read()
dl = re.search(r'^target datalayout = "([^"]*)"', text, re.M).group(1)
if dl != EXPECT_DL:
    sys.exit(f'unexpected data layout {dl}')
text = re.sub(r'^target triple = "[^"]*"', 'target triple = "thumbv7em-unknown-none-eabihf"', text, count=1, flags=re.M)
# The exact cpu/feature strings clang gives Cortex-M4 hard-float code: Kotlin functions and the C runtime then
# carry identical attributes, so LTO may inline runtime hooks (UpdateHeapRef, EnterFrame...) into Kotlin code.
M4_CPU = '"target-cpu"="cortex-m4"'
M4_FEATURES = '"target-features"="+armv7e-m,+dsp,+fp16,+hwdiv,+thumb-mode,+vfp2sp,+vfp3d16sp,+vfp4d16sp,-aes,-bf16,-cdecp0,-cdecp1,-cdecp2,-cdecp3,-cdecp4,-cdecp5,-cdecp6,-cdecp7,-crc,-crypto,-d32,-dotprod,-fp-armv8,-fp-armv8d16,-fp-armv8d16sp,-fp-armv8sp,-fp16fml,-fp64,-fullfp16,-hwdiv-arm,-i8mm,-lob,-mve,-mve.fp,-neon,-pacbti,-ras,-sb,-sha2,-vfp2,-vfp3,-vfp3d16,-vfp3sp,-vfp4,-vfp4d16,-vfp4sp"'
text = re.sub(r'"target-cpu"="[^"]*"', M4_CPU, text)
text = re.sub(r'"target-features"="[^"]*"', M4_FEATURES, text)
text = re.sub(r'^(attributes #\d+ = )\{ \}$', lambda m: m.group(1) + '{ "kmicro"="retargeted" }', text, flags=re.M)
# Definitions with no attribute group at all (the cinterop bridges and wrappers that bridges.py copies) would carry
# no cpu/features: the inliner then refuses to put a Cortex-M4 callee (hw.c's one-instruction helpers) into them.
NOATTR = re.compile(r'^(define [^\n]*\)) \{$', re.M)
if NOATTR.search(text):
    text = NOATTR.sub(r'\1 #9999 {', text)
    text += f'\nattributes #9999 = {{ nounwind {M4_CPU} {M4_FEATURES} }}\n'
if '--size' in args:  # optimize for size: LLVM's minsize/optsize on every Kotlin function (= clang -Oz)
    # --hot REGEX: functions whose name matches keep full speed optimisation (their attribute group is cloned
    # without minsize/optsize), e.g. code that runs in a real-time interrupt.
    hot = re.compile(args[args.index('--hot') + 1]) if '--hot' in args else None
    groups = {m.group(1): m.group(2) for m in re.finditer(r'^attributes #(\d+) = \{ (.*) \}$', text, re.M)}
    clones = {}
    if hot:
        def retag(m):
            name, grp = m.group(2), m.group(4)
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
        print(f'size: minsize everywhere except {n_hot} hot functions')
if '--no-tls' in args:
    text = TLS_RE.sub('', text)
if '--single-core' in args:
    # Every access to a file's globals first checks its init state with an acquire load (a DMB on the M4, and LLVM
    # may not hoist it out of a loop). kmicro runs Kotlin on one core in one thread, and interrupt handlers never
    # initialise globals (the runtime stops if they try), so a plain load is exact: no barrier, hoistable.
    text, n = re.subn(r'load atomic (i32), ptr (@"state_global\$[^"]*") acquire, align 4', r'load \1, ptr \2, align 4', text)
    print(f'single-core: {n} init-state loads made plain')
if '--drop-ctors' in args:
    text = re.sub(r'^@llvm\.global_ctors = .*$', '', text, count=1, flags=re.M)
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
