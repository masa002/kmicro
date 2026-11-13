"""Kotlin sources -> Cortex-M4 LTO objects, the steps every kmicro build shares.

    compile_ir()   the official kotlinc-native 2.4.21, unmodified, for linux_arm32_hfp (a 32-bit EABI target whose
                   data layout equals thumbv7em's): textual LLVM IR after Codegen (+ the C stubs of cinterop)
    retarget()     toolchain/retarget.py: thumbv7em triple, Cortex-M4 attributes, TLS -> plain storage ...
    lto_object()   clang -flto: the IR becomes an object that ld.lld optimises together with the runtime and the C code
    bridges()      the cinterop call bridges (toolchain/bridges.py), when the program calls C through cinterop
    cinterop()     a .def file -> klib (C declarations Kotlin can call)
    add_c_aliases()   C names for Kotlin functions (`crc32_update` -> app.crc32Update): C calls Kotlin directly
    add_init_all()    one C-callable function that initialises a package's globals (files, objects) at boot
    build()        all of the above in order: Kotlin sources -> the objects to link (tools/kbuild.py is its command line)

A program built this way runs on the kmicro runtime (runtime/): see docs/how-it-works.md.
"""
import json
import os
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import paths  # noqa: E402

KOTLINC_BASE = ['-target', 'linux_arm32_hfp', '-p', 'static', '-opt', '-nomain']


def sh(args, **kw):
    r = subprocess.run([str(a) for a in args], capture_output=True, text=True, errors='replace', **kw)
    if r.returncode != 0:
        sys.exit(f'FAILED: {" ".join(map(str, args))[:400]}\n{r.stdout[-3000:]}{r.stderr[-3000:]}')
    return r


def stale(target, *sources):
    target = Path(target)
    return not target.exists() or any(target.stat().st_mtime < Path(s).stat().st_mtime for s in sources)


def argfile(path, args):
    """kotlinc's argument file: UTF-8, every argument quoted (a path may hold spaces; a backslash escapes)."""
    Path(path).write_text(''.join('"' + str(a).replace('\\', '\\\\').replace('"', '\\"') + '"\n' for a in args),
                          encoding='utf-8')


def kotlin_files(srcs):
    """The Kotlin files a compile reads: each source, a folder standing for the .kt files under it. A missing one is
    an error."""
    files = []
    for s in map(Path, srcs):
        if not s.exists():
            sys.exit(f'kmicro: Kotlin source not found: {s}')
        files += sorted(s.rglob('*.kt')) if s.is_dir() else [s]
    return files


def _stamps(files):
    """One line per file (every file under a folder): path, size, modification time."""
    lines = []
    for f in map(Path, files):
        if not f.exists():
            sys.exit(f'kmicro: not found: {f}')
        for x in (sorted(y for y in f.rglob('*') if y.is_file()) if f.is_dir() else [f]):
            st = x.stat()
            lines.append(f'{os.path.abspath(x)} {st.st_size} {st.st_mtime_ns}')
    return lines


def _compiler_key():
    jar = paths.kotlin_native() / 'konan/lib/kotlin-native-compiler-embeddable.jar'
    return [f'kotlin-native {os.path.abspath(paths.kotlin_native())} {paths.kotlin_native_version()}',
            *_stamps([jar] if jar.exists() else [])]


def _up_to_date(keyfile, key):
    """Whether the last successful run had exactly this key (its arguments, compiler and input files). When not, the
    old key is removed first, so a failed or interrupted run is never taken as current."""
    keyfile = Path(keyfile)
    if keyfile.exists() and keyfile.read_text(encoding='utf-8') == key:
        return True
    keyfile.unlink(missing_ok=True)
    return False


def compile_ir(srcs, out, extra=(), deps=(), force=False):
    """kotlinc-native -> out/ir/out.Codegen.ll and out/ir/out.LinkBitcodeDependencies.ll. Skipped while the saved IR
    came from the same arguments, the same compiler and unchanged sources and dependencies (klibs): any difference,
    a removed source included, recompiles. Returns the compiler's warnings (empty when skipped)."""
    out = Path(out)
    files = kotlin_files(srcs)
    o = Path(os.path.abspath(out))             # absolute: paths.run_kn may start the compiler in another folder
    args = [Path(os.path.abspath(s)).as_posix() for s in srcs] + KOTLINC_BASE + [str(a) for a in extra] + [
        '-o', (o / 'lib').as_posix(), '-Xsave-llvm-ir-after=Codegen,LinkBitcodeDependencies',
        f'-Xsave-llvm-ir-directory={(o / "ir").as_posix()}', f'-Xtemporary-files-dir={(o / "tmp").as_posix()}']
    key = '\n'.join(['[arguments]', *args, '[compiler]', *_compiler_key(), '[inputs]', *_stamps([*files, *deps])])
    if (out / 'ir/out.Codegen.ll').exists() and _up_to_date(out / 'ir/key.txt', key) and not force:
        return []
    (out / 'ir').mkdir(parents=True, exist_ok=True)
    (out / 'tmp').mkdir(exist_ok=True)
    (out / 'ir/key.txt').unlink(missing_ok=True)
    argfile(out / 'args.txt', args)
    print(f'kotlinc-native: compiling {len(files)} file{"s" if len(files) != 1 else ""}...', file=sys.stderr,
          flush=True)
    r = paths.run_kn('kotlinc-native', ['@' + (out / 'args.txt').as_posix()])
    errors, warnings = compiler_messages(r.stdout + r.stderr)
    if r.returncode != 0:
        sys.exit('kotlinc-native FAILED:\n' + '\n'.join(errors + warnings or
                                                        (r.stdout + r.stderr).splitlines()[-30:]))
    (out / 'ir/key.txt').write_text(key, encoding='utf-8')
    return warnings


TARGET_NOTICE = 'warning: target linux_arm32_hfp is deprecated'   # kmicro's choice, not the program's
MESSAGE = re.compile(r'^(?:\S.*?:\d+:\d+: )?(error|warning|note|exception): ')
API_CPP_HINT = ("kmicro: kotlinc-native's C export (-p static) cannot handle the name of a public declaration (see "
                'api.cpp above): make it internal or private, or give it a plain name')


def compiler_messages(output):
    """kotlinc-native's output -> (errors, warnings): each message with the lines that follow it (source line and
    caret), without the linux_arm32_hfp notice, the C adapter's (api.cpp) warnings and Java stack traces. A failure
    of the C adapter keeps clang's errors and adds a hint."""
    blocks = []
    for line in output.splitlines():
        m = MESSAGE.match(line)
        if m and blocks and blocks[-1][0] == 'exception':
            m = None                           # the exception's own copy of the messages
        if m and m.group(1) == 'exception' and any(b[0] == 'error' for b in blocks):
            break                              # the failure already reported, again with a stack trace
        if m:
            blocks.append([m.group(1), line])
        elif blocks and line.strip() and not line.startswith(('\tat ', ' * ', 'output:')):
            blocks[-1].append(line)
    api_cpp = [b for b in blocks if 'api.cpp:' in b[1]]
    errors, warnings = [], []
    for kind, *lines in blocks:
        text = '\n'.join(lines)
        if lines[0].startswith(TARGET_NOTICE) or ('api.cpp:' in lines[0] and kind == 'warning'):
            continue
        if kind == 'note' and not any(k == 'error' for k, *_ in api_cpp):
            continue
        (warnings if kind == 'warning' else errors).append(text)
    if any(k == 'error' for k, *_ in api_cpp):
        errors.append(API_CPP_HINT)
    return list(dict.fromkeys(errors)), list(dict.fromkeys(warnings))


def retarget(ir, ll_out, *opts):
    sys.stderr.write(sh([sys.executable, HERE / 'retarget.py', ir, ll_out, *opts]).stderr)   # its summaries
    return Path(ll_out)


def lto_object(ll, obj, opt='-O2'):
    sh([paths.clang(), *paths.TARGET_M4F, opt, '-flto', '-c', '-x', 'ir', ll, '-o', obj])
    return Path(obj)


def bridges(out):
    """The cinterop bridges of a compile_ir() output as an LTO object, or [] when the program calls no C."""
    out = Path(out)
    lbd = out / 'ir/out.LinkBitcodeDependencies.ll'
    if not lbd.exists() or 'knbridge' not in lbd.read_text(encoding='utf-8', errors='replace'):
        return []
    sh([sys.executable, HERE / 'bridges.py', lbd, out / 'bridges_raw.ll'])
    retarget(out / 'bridges_raw.ll', out / 'bridges.ll')
    return [lto_object(out / 'bridges.ll', out / 'bridges.o')]


def cinterop(def_file, out_base, include_dirs=(), deps=(), force=False):
    """def_file -> out_base.klib, rebuilt when the .def, a dependency (typically the headers), the include folders or
    the compiler change."""
    klib = Path(str(out_base) + '.klib')
    key = '\n'.join(['[arguments]', os.path.abspath(def_file), *(os.path.abspath(d) for d in include_dirs),
                     os.path.abspath(out_base), '[compiler]', *_compiler_key(), '[inputs]',
                     *_stamps([def_file, *deps])])
    keyfile = Path(str(out_base) + '.key.txt')
    if force or not klib.exists() or not _up_to_date(keyfile, key):
        Path(out_base).parent.mkdir(parents=True, exist_ok=True)
        keyfile.unlink(missing_ok=True)
        # cinterop takes no argument file: its arguments go on Java's command line (paths.arg_path)
        args = ['-def', paths.arg_path(def_file), '-target', 'linux_arm32_hfp']
        for d in include_dirs:
            args += ['-compiler-option', '-I' + paths.arg_path(d)]
        args += ['-o', paths.arg_path(out_base)]
        r = paths.run_kn('cinterop', args)
        if r.returncode != 0:
            sys.exit('cinterop FAILED:\n' + (r.stdout + r.stderr)[-3000:])
        keyfile.write_text(key, encoding='utf-8')
    return klib


def camel(cname):
    """C name -> the Kotlin function name kmicro expects, in lowerCamelCase: crc32_update -> crc32Update,
    DMA1_Channel3_IRQHandler -> dma1Channel3IrqHandler, SysTick_Handler -> sysTickHandler, TIM1_UP_TIM16_IRQHandler
    -> tim1UpTim16IrqHandler (an all-caps word keeps only its first capital), EXTI15_10_IRQHandler ->
    exti15_10IrqHandler (an underscore stays between two numbers)."""
    suffix = ''
    for c_end, k_end in (('_IRQHandler', 'IrqHandler'), ('_Handler', 'Handler')):
        if cname.endswith(c_end) and len(cname) > len(c_end):
            cname, suffix = cname[:-len(c_end)], k_end
            break
    out = ''
    for w in filter(None, cname.split('_')):
        if not out:
            w = w.lower() if w.isupper() else w[0].lower() + w[1:]
        else:
            w = w[0] + w[1:].lower() if w.isupper() else w[0].upper() + w[1:]
            if out[-1].isdigit() and w[0].isdigit():
                out += '_'
        out += w
    return (out or cname) + suffix


def legacy_camel(cname):
    """The Kotlin name earlier kmicro versions expected (SysTickHandler, tim1UPTIM16IrqHandler, USBSend), still
    accepted with a note."""
    if cname.endswith('_IRQHandler'):
        head, *rest = cname[:-len('_IRQHandler')].split('_')
        return head.lower() + ''.join(w[:1].upper() + w[1:] for w in rest) + 'IrqHandler'
    head, *rest = cname.split('_')
    return head + ''.join(w[:1].upper() + w[1:] for w in rest)


def kotlin_names(cname):
    """The Kotlin names that may implement a C name: camel(), then the legacy spelling when it differs."""
    return list(dict.fromkeys([camel(cname), legacy_camel(cname)]))


def _type_list(params):
    return ', '.join(p.split()[0] for p in filter(None, (x.strip() for x in params.split(','))))


IR_TYPES = ('void', 'i1', 'i8', 'i16', 'i32', 'i64', 'float', 'double', 'ptr', '...')


def ir_signature(ret_words, params):
    """IR declaration parts -> ((return type, extension), [(parameter type, extension)]): the ABI a C caller sees.
    The extension is signext, zeroext or '' (an i8/i16/i1 argument is widened by the caller)."""
    def one(words):
        t = next((w for w in words if w in IR_TYPES or w.startswith(('{', '%', '['))), '?')
        return t, next((w for w in words if w in ('signext', 'zeroext')), '')
    return one(ret_words.split()), [one(p.split()) for p in filter(None, (x.strip() for x in params.split(',')))]


def kotlin_functions(ll_text, package):
    """Top-level functions of `package` defined in the IR: Kotlin name -> [(symbol, return type, parameter types,
    ir_signature())]."""
    defs = {}
    pat = r'^define ([^@]*?)@"(kfun:' + re.escape(package) + r'#([A-Za-z0-9_]+)\([^"]*)"\(([^)]*)\)'
    for m in re.finditer(pat, ll_text, re.M):
        ret = [w for w in m.group(1).split() if w not in ('internal', 'dso_local', 'zeroext', 'signext', 'noundef',
                                                          'nonnull', 'hidden', 'local_unnamed_addr')][-1]
        defs.setdefault(m.group(3), []).append((m.group(2), ret, _type_list(m.group(4)),
                                                ir_signature(m.group(1), m.group(4))))
    return defs


C_PRIMITIVES = {'kotlin.Int', 'kotlin.Long', 'kotlin.Short', 'kotlin.Byte', 'kotlin.Float', 'kotlin.Double',
                'kotlin.Boolean', 'kotlin.Char', 'kotlin.UInt', 'kotlin.ULong', 'kotlin.UShort', 'kotlin.UByte'}


def kotlin_signature(sym):
    """A Kotlin function symbol -> (parameter types, return type), '' for Unit:
    'kfun:app#hello(kotlin.Int;kotlin.String){}kotlin.String' -> (['kotlin.Int', 'kotlin.String'], 'kotlin.String')."""
    s = sym.split('#', 1)[1]
    start = s.index('(')
    depth, params, cur = 0, [], ''
    for i in range(start + 1, len(s)):
        c = s[i]
        if c == ')' and depth == 0:
            break
        if c in '<(':
            depth += 1
        elif c in '>)':
            depth -= 1
        if c == ';' and depth == 0:
            params.append(cur)
            cur = ''
        else:
            cur += c
    params += [cur] if cur else []
    rest = s[i + 1:]
    return params, rest[rest.index('}') + 1:] if rest.startswith('{') else rest


def crosses_to_c(kotlin_type, result=False):
    """Whether a Kotlin parameter or result type has a plain C equivalent: a primitive (not nullable: that is a boxed
    object), an unsigned number, a CPointer or NativePtr, or Unit ('') or Nothing (void) as a result."""
    return (kotlin_type in C_PRIMITIVES or (result and kotlin_type in ('', 'kotlin.Nothing'))
            or kotlin_type.startswith('kotlinx.cinterop.CPointer<')
            or kotlin_type in ('kotlin.native.internal.NativePtr', 'kotlinx.cinterop.NativePtr'))


def _show_sig(sig):
    (rt, rx), ps = sig
    return f'{rt} ({", ".join(t for t, _ in ps)})'


def check_c_signature(cname, sym, kotlin_sig, c_sig=None, c_text=None):
    """Error messages (empty when fine) for a C name that becomes an alias of the Kotlin function `sym`: every Kotlin
    parameter and result must have a plain C type, and the C prototype (c_sig, an ir_signature() of what clang made
    of it) must have the same IR types and argument extensions."""
    params, ret = kotlin_signature(sym)
    kname = sym.split('#', 1)[1].split('(', 1)[0]
    bad = [f'returns {ret}'] if not crosses_to_c(ret, result=True) else []
    bad += [f'takes {t}' for t in params if not crosses_to_c(t)]
    if bad:
        return [f'{cname}: Kotlin {kname} {" and ".join(bad)}; only primitives, unsigned numbers and CPointer can '
                'cross to C (pass other data through a CPointer, or keep it on the Kotlin side)']
    if c_sig is None or c_sig == kotlin_sig:
        return []
    if c_sig[1] == [('...', '')] and not kotlin_sig[1] and c_sig[0] == kotlin_sig[0]:
        return []                              # `void f();` (no parameter list) for a Kotlin function without any
    if c_sig[1] and c_sig[1][-1][0] == '...':
        return [f'{cname}: the C prototype is variadic or has no parameter list; declare it as `{cname}(void)` or '
                'with its parameters']
    return [f'{cname}: the C prototype {c_text or _show_sig(c_sig)} does not match Kotlin {kname}({";".join(params)})'
            f'{": " + ret if ret else ""} (C: {_show_sig(c_sig)}; Kotlin: {_show_sig(kotlin_sig)}'
            + ('; signed/unsigned differs' if [t for t, _ in c_sig[1]] == [t for t, _ in kotlin_sig[1]]
               and c_sig[0][0] == kotlin_sig[0][0] else '') + ')']


def c_signatures(headers, names, include_dirs=(), defines=(), work=None):
    """C name -> ir_signature() of its prototype as clang lowers it for the Cortex-M4 (the ABI a C caller uses)."""
    if not names:
        return {}
    headers = [Path(h).resolve() for h in headers]
    src = Path(work or '.') / 'c_api_check.c'
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_text(''.join(f'#include "{h.as_posix()}"\n' for h in headers)
                   + 'void *const kmicro_c_api[] = {\n' + ''.join(f'    (void *)&{n},\n' for n in names) + '};\n',
                   encoding='utf-8')
    dirs = [*dict.fromkeys(h.parent for h in headers), *include_dirs]
    ll = _clang_c([*c_flags(headers[0], dirs, defines), '-S', '-emit-llvm', '-O0', '-o', '-', src],
                  ', '.join(map(str, headers)))
    sigs = {}
    for m in re.finditer(r'^declare ([^@]*)@"?([\w.$]+)"?\(([^)]*)\)', ll, re.M):
        sigs[m.group(2)] = ir_signature(m.group(1), m.group(3))
    return sigs


def add_c_aliases(ll_text, cnames, package, prefix='', c_sigs=None, c_texts=None):
    """`@<prefix><cname> = alias ...` for every C name whose camelCase Kotlin function exists in `package`. Returns the
    alias lines and the C names that found no Kotlin function. Two C names with one Kotlin name are an error, and so
    is a Kotlin function whose types cannot cross to C or (with c_sigs from c_signatures()) do not match the C
    prototype."""
    cnames = list(dict.fromkeys(cnames))
    seen = {}
    for cname in cnames:
        other = seen.setdefault(camel(cname), cname)
        if other != cname:
            sys.exit(f'kmicro: the C names {other} and {cname} both become the Kotlin name {camel(cname)}: rename '
                     'one of them')
    defs = kotlin_functions(ll_text, package)
    lines, missing, errors = [], [], []
    for cname in cnames:
        name = next((n for n in kotlin_names(cname) if n in defs), None)
        if name is None:
            missing.append(cname)
            continue
        if name != camel(cname):
            print(f'kmicro: note: {cname} is implemented by {name}, an old spelling: rename it {camel(cname)} (the '
                  'old one will stop working)', file=sys.stderr)
        k = defs[name]
        if len(k) > 1:
            sys.exit(f'kmicro: overloaded Kotlin function for {cname}: {[x[0] for x in k]}')
        sym, ret, params, sig = k[0]
        errors += check_c_signature(cname, sym, sig, (c_sigs or {}).get(cname), (c_texts or {}).get(cname))
        lines.append(f'@{prefix}{cname} = alias {ret} ({params}), ptr @"{sym}"')
    if errors:
        sys.exit('kmicro: ' + '\nkmicro: '.join(errors))
    return lines, missing


def add_init_all(ll_text, package, name='kt_init_all'):
    """`void <name>(void)`: the globals of `package` and its sub-packages created now, file-level ones and those of
    object declarations (and companion objects). Kotlin initialises each on first use; called at boot (thread context,
    before interrupts), no interrupt handler ever does that allocation. A package with no Kotlin code is an error."""
    if package:
        mine = re.escape(package) + r'[.$][^"]*'
    else:                                      # the root package: its files, and classes outside any package
        mine = r'(?:<root>\$[^"]*|[A-Z][^"$]*)'
    pairs = sorted(set(re.findall(
        r'call void @CallInitGlobalPossiblyLock\(ptr noundef (@"state_global\$' + mine + r'"), '
        r'ptr noundef (@"kfun:[^"]*\$init_global[^"]*")\)', ll_text)))
    if not pairs and not re.search(r'^define [^\n]*@"kfun:' + re.escape(package) + r'[#.]', ll_text, re.M):
        sys.exit(f'kmicro: init_all (--init-all): no Kotlin code in package {package or "<root>"} (--package)')
    return [f'define void @{name}() {{',
            *[f'  call void @CallInitGlobalPossiblyLock(ptr {st}, ptr {fn})' for st, fn in pairs],
            '  ret void', '}']


def c_flags(header, include_dirs=(), defines=()):
    """clang flags that read a C header as qbuild compiles C: Cortex-M4F, newlib, runtime/ and support/ on the include
    path, then the header's own folder and `include_dirs`; `defines` as NAME or NAME=VALUE."""
    root = HERE.parent
    return [*paths.TARGET_M4F, '-isystem', paths.newlib_include(), '-I', root / 'runtime', '-I', root / 'support',
            '-I', Path(header).resolve().parent, *(x for d in include_dirs for x in ('-I', d)),
            *('-D' + d for d in defines)]


def _clang_c(args, what):
    r = subprocess.run([str(a) for a in [paths.clang(), '-x', 'c', '-std=gnu11', *args]], capture_output=True,
                       text=True, encoding='utf-8', errors='replace')
    if r.returncode != 0:
        errs = [l for l in r.stderr.splitlines() if ' error: ' in l or l.startswith('error:')] or r.stderr.splitlines()
        sys.exit(f'kmicro: clang cannot read {what}:\n' + '\n'.join(errs[:10])
                 + '\n(a header it includes is not found? add its folder with -I)')
    return r.stdout


def c_prototypes(*headers, include_dirs=(), defines=()):
    """Names of the functions the headers themselves declare without a body, exactly as a C compiler reads them
    (clang's syntax tree): extern prototypes and prototypes made by macros count; static inline functions, calls
    inside their bodies, inactive #if blocks and the headers they include do not."""
    return list(c_declarations(*headers, include_dirs=include_dirs, defines=defines))


def c_declarations(*headers, include_dirs=(), defines=()):
    """c_prototypes() with each function's C type: name -> 'int32_t (int32_t)'."""
    names = {}
    for h in headers:
        h = Path(h)
        if not h.exists():
            sys.exit(f'kmicro: header not found: {h}')
        tree = json.loads(_clang_c([*c_flags(h, include_dirs, defines), '-fsyntax-only', '-Xclang', '-ast-dump=json',
                                    h.resolve()], h))
        here, state, bodies = os.path.normcase(str(h.resolve())), [None], set()

        def walk(x):                           # clang writes a location's file only when it changes, in this order
            if isinstance(x, dict):
                if 'offset' in x and 'file' in x:
                    state[0] = x['file']
                for v in x.values():
                    walk(v)
            elif isinstance(x, list):
                for v in x:
                    walk(v)
        found = []
        for node in tree.get('inner', []):
            walk(node.get('loc', {}))
            in_header = state[0] is not None and os.path.normcase(os.path.abspath(state[0])) == here
            walk({k: v for k, v in node.items() if k != 'loc'})
            if node.get('kind') != 'FunctionDecl' or node.get('isImplicit') or not in_header:
                continue
            if any(c.get('kind') == 'CompoundStmt' for c in node.get('inner', [])):
                bodies.add(node['name'])
            elif node.get('storageClass') != 'static':
                found.append((node['name'], node.get('type', {}).get('qualType', '?')))
        names.update((n, t) for n, t in found if n not in bodies and n not in names)
    return names


def build(srcs, out, libs=(), deps=(), c_api=(), package=None, init_all=None, size=False, hot=None, force=False,
          kotlinc_args=(), include_dirs=()):
    """Kotlin sources -> [out/k.o] (+ out/bridges.o when the program calls C through cinterop), ready to link with
    the kmicro runtime.

    libs     klibs the sources use (cinterop output); deps: other files whose change means a recompile
    c_api    C headers whose prototypes the Kotlin code implements: `int32_t gc_chains(int32_t)` becomes a C name for
             the Kotlin function <package>.gcChains, so C calls Kotlin by plain names (a prototype without its
             Kotlin function is an error; the init_all name may be declared there too)
    init_all the name of a generated C function `void <init_all>(void)` that initialises the globals of <package> and
             its sub-packages, objects included: called at boot, before interrupts, it leaves no first-use
             initialisation of that code to a handler (add_init_all)
    size     minsize for every Kotlin function except those whose symbol matches the regex `hot`
    kotlinc_args  more kotlinc-native options (-Xbinary=latin1Strings=true, -opt-in=..., -language-version ...)
    include_dirs  folders the c_api headers include from (besides their own, runtime/, support/ and newlib)
    """
    out = Path(out)
    if hot and not size:
        sys.exit('kmicro: hot (--hot) needs size (--size)')
    extra = [*(x for lib in libs for x in ('-l', Path(os.path.abspath(lib)).as_posix())), *kotlinc_args]
    for w in compile_ir(srcs, out, extra, [*libs, *deps], force):
        print(w, file=sys.stderr)             # (stdout is kbuild's list of objects)
    ll = retarget(out / 'ir/out.Codegen.ll', out / 'm4.ll', '--no-tls', '--single-core',
                  *(['--size', *(['--hot', hot] if hot else [])] if size else []))
    if c_api or init_all:
        if package is None:
            sys.exit('kmicro: c_api and init_all (--c-api, --init-all) need the Kotlin package (--package)')
        text = ll.read_text(encoding='utf-8')
        decls = c_declarations(*c_api, include_dirs=include_dirs)
        names = [n for n in decls if n != init_all]
        lines, missing = add_c_aliases(text, names, package, c_sigs=c_signatures(c_api, names, include_dirs, work=out),
                                       c_texts=decls)
        if missing:
            sys.exit(f'kmicro: no Kotlin function in package {package} for: '
                     + ', '.join(f'{c} (expected {camel(c)})' for c in missing))
        if init_all:
            lines += add_init_all(text, package, init_all)
        ll.write_text(text + '\n' + '\n'.join(lines) + '\n', encoding='utf-8', newline='\n')
    return [lto_object(ll, out / 'k.o'), *bridges(out)]
