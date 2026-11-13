"""Kotlin sources -> Cortex-M4 LTO objects, the steps every kmicro build shares.

    compile_ir()   the official kotlinc-native 2.4.21, unmodified, for linux_arm32_hfp (a 32-bit EABI target whose
                   data layout equals thumbv7em's): textual LLVM IR after Codegen (+ the C stubs of cinterop)
    retarget()     toolchain/retarget.py: thumbv7em triple, Cortex-M4 attributes, TLS -> plain storage ...
    lto_object()   clang -flto: the IR becomes an object that ld.lld optimises together with the runtime and the C code
    bridges()      the cinterop call bridges (toolchain/bridges.py), when the program calls C through cinterop
    cinterop()     a .def file -> klib (C declarations Kotlin can call)
    add_c_aliases()   C names for Kotlin functions (`crc32_update` -> fw.crc32Update), so C code calls Kotlin directly
    add_init_all()    one C-callable function that initialises every Kotlin file's globals at boot
    build()        all of the above in order: Kotlin sources -> the objects to link (tools/kbuild.py is its command line)

A program built this way runs on the kmicro runtime (runtime/): see docs/how-it-works.md.
"""
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


def camel(snake):
    """C name -> the Kotlin function name kmicro expects: crc32_update -> crc32Update,
    DMA1_Channel3_IRQHandler -> dma1Channel3IrqHandler."""
    if snake.endswith('_IRQHandler'):
        head, *rest = snake[:-len('_IRQHandler')].split('_')
        return head.lower() + ''.join(w[:1].upper() + w[1:] for w in rest) + 'IrqHandler'
    head, *rest = snake.split('_')
    return head + ''.join(w[:1].upper() + w[1:] for w in rest)


def _type_list(params):
    return ', '.join(p.split()[0] for p in filter(None, (x.strip() for x in params.split(','))))


def kotlin_functions(ll_text, package):
    """Top-level functions of `package` defined in the IR: Kotlin name -> [(symbol, return type, parameter types)]."""
    defs = {}
    pat = r'^define ([^@]*?)@"(kfun:' + re.escape(package) + r'#([A-Za-z0-9_]+)\([^"]*)"\(([^)]*)\)'
    for m in re.finditer(pat, ll_text, re.M):
        ret = [w for w in m.group(1).split() if w not in ('internal', 'dso_local', 'zeroext', 'signext', 'noundef',
                                                          'nonnull', 'hidden', 'local_unnamed_addr')][-1]
        defs.setdefault(m.group(3), []).append((m.group(2), ret, _type_list(m.group(4))))
    return defs


def add_c_aliases(ll_text, cnames, package, prefix=''):
    """`@<prefix><cname> = alias ...` for every C name whose camelCase Kotlin function exists in `package`. Returns the
    alias lines and the C names that found no Kotlin function."""
    defs = kotlin_functions(ll_text, package)
    lines, missing = [], []
    for cname in cnames:
        k = defs.get(camel(cname))
        if not k:
            missing.append(cname)
            continue
        if len(k) > 1:
            sys.exit(f'overloaded Kotlin function for {cname}: {[x[0] for x in k]}')
        sym, ret, params = k[0]
        lines.append(f'@{prefix}{cname} = alias {ret} ({params}), ptr @"{sym}"')
    return lines, missing


def add_init_all(ll_text, package, name='kt_init_all'):
    """`void <name>(void)`: every file-level global of `package` created now. Kotlin initialises a file on first use;
    called at boot (thread context, before interrupts), no interrupt handler ever does that allocation."""
    pairs = sorted(set(re.findall(
        r'call void @CallInitGlobalPossiblyLock\(ptr noundef (@"state_global\$' + re.escape(package) + r'\$[^"]*"), '
        r'ptr noundef (@"kfun:' + re.escape(package) + r'\.\$init_global\$[^"]*")\)', ll_text)))
    return [f'define void @{name}() {{',
            *[f'  call void @CallInitGlobalPossiblyLock(ptr {st}, ptr {fn})' for st, fn in pairs],
            '  ret void', '}']


def c_prototypes(*headers):
    """Names of the functions the headers declare (prototypes only: no static inline bodies, typedefs, externs)."""
    names = []
    for h in headers:
        s = re.sub(r'/\*.*?\*/|//[^\n]*', '', Path(h).read_text(encoding='utf-8', errors='replace'), flags=re.S)
        s = re.sub(r'\\\n', ' ', s)
        s = re.sub(r'^[ \t]*#.*$', '', s, flags=re.M)          # preprocessor lines would glue onto the next prototype
        for stmt in re.split(r';|\{|\}', s):
            st = ' '.join(stmt.split())
            if not st or st.startswith(('#', 'typedef', 'extern', 'static', 'return')) or '=' in st:
                continue
            m = re.search(r'\b([A-Za-z_]\w*)\s*\(((?:[^()]|\([^()]*\))*)\)\s*(?:__attribute__\(\(.*\)\))?\s*$', st)
            if m and m.group(1) not in names and not re.match(r'^(if|while|for|switch|sizeof)$', m.group(1)):
                names.append(m.group(1))
    return names


def build(srcs, out, libs=(), deps=(), c_api=(), package=None, init_all=None, size=False, hot=None, force=False):
    """Kotlin sources -> [out/k.o] (+ out/bridges.o when the program calls C through cinterop), ready to link with
    the kmicro runtime.

    libs     klibs the sources use (cinterop output); deps: other files whose change means a recompile
    c_api    C headers whose prototypes the Kotlin code implements: `int32_t gc_chains(int32_t)` becomes a C name for
             the Kotlin function <package>.gcChains, so C calls Kotlin by plain names (a prototype without its
             Kotlin function is an error)
    init_all the name of a generated C function `void <init_all>(void)` that initialises every file-level global of
             <package>: called at boot, before interrupts, it leaves no first-use initialisation to a handler
    size     minsize for every Kotlin function except those whose symbol matches the regex `hot`
    """
    out = Path(out)
    for w in compile_ir(srcs, out, [x for lib in libs for x in ('-l', lib)], [*libs, *deps], force):
        print(w, file=sys.stderr)             # (stdout is kbuild's list of objects)
    ll = retarget(out / 'ir/out.Codegen.ll', out / 'm4.ll', '--no-tls', '--single-core',
                  *(['--size', *(['--hot', hot] if hot else [])] if size else []))
    if c_api or init_all:
        if not package:
            sys.exit('kmicro: c_api and init_all need the Kotlin package')
        text = ll.read_text(encoding='utf-8')
        lines, missing = add_c_aliases(text, c_prototypes(*c_api), package)
        if missing:
            sys.exit(f'kmicro: no Kotlin function in package {package} for: '
                     + ', '.join(f'{c} (expected {camel(c)})' for c in missing))
        if init_all:
            lines += add_init_all(text, package, init_all)
        ll.write_text(text + '\n' + '\n'.join(lines) + '\n', encoding='utf-8', newline='\n')
    return [lto_object(ll, out / 'k.o'), *bridges(out)]
