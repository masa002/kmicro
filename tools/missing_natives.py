#!/usr/bin/env python3
"""Which runtime functions the Kotlin/Native stdlib needs, and which of them kmicro does not provide.

    python tools/missing_natives.py [-v] [--check] [--ir FILE.ll ...]

The stdlib's natives are its @GCUnsafeCall/@SymbolName declarations, read from the sources archive that ships with
Kotlin/Native (sources/kotlin-stdlib-native-sources.zip). What kmicro defines comes from compiling runtime/ to LLVM
IR. Each stdlib native is one of:

    implemented   defined in runtime/
    unsupported   defined in runtime/unsupported.c: a call stops the program with a message naming the Kotlin API
    Objective-C   part of the Objective-C interop, which only Apple targets use
    missing       not defined: a board link that needs it fails, and qbuild stubs it with a panic naming the symbol

--ir also checks the functions compiled programs declare (their m4.ll, e.g. build/diff/kmicro/*/m4.ll), which adds
the runtime calls the compiler emits itself, such as LookupInterfaceTableRecord. A declared function that runtime/
defines must have the same LLVM signature (types, and zeroext/signext on narrow integers): link-time optimisation
treats a call through a mismatched signature as undefined behaviour. A declared function that neither runtime/ nor
newlib/libgcc defines is listed like a missing native. A file that declares no function is an error: a compiled
Kotlin program always declares runtime functions, so such a file is empty, cut or not LLVM IR.

    -v       list the implemented and Objective-C natives too
    --check  exit 1 when a native is missing or a signature differs
"""
import glob
import re
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'toolchain'))
import paths  # noqa: E402

UNSUPPORTED_C = 'unsupported.c'
OBJC_FILE = re.compile(r'ObjectiveC|ObjCExport|ForeignException')
OBJC_NAME = re.compile(r'objc|ObjC|_NS[A-Z]|Block_copy|ObjectHolder|^CreateKotlinObjCClass|^GetObjCKotlinTypeInfo|'
                       r'^MissingInitImp|DoesObjectConformToProtocol|IsObjectKindOfClass')
NATIVE = re.compile(r'@(?:GCUnsafeCall|SymbolName)\(\s*"([^"]+)"')
TOKEN = re.compile(r'[A-Za-z_]\w*\([^()]*\)|<[^<>]*>|\{[^{}]*\}|\[[^\[\]]*\]|"[^"]*"|\S+')
TYPE = re.compile(r'^(void|i\d+|half|bfloat|float|double|fp128|ptr|%[\w.$"]+|<.*>|\{.*\}|\[.*\]|\.\.\.)$')


def kotlin_api(lines, i, owners):
    """'ByteArray.getIntAt', 'GC.getTargetHeapBytes': the function declared after the annotation on line i."""
    for line in lines[i:i + 12]:
        m = re.search(r'\bfun\s+(?:<.*?>\s+)?(\S+?)\s*\(', line)
        if m:
            return '.'.join([*owners, m.group(1)])
    return '?'


def stdlib_natives():
    """{symbol: [(file in the archive, Kotlin declaration)]} of the stdlib shipped with Kotlin/Native."""
    archive = paths.kotlin_native() / 'sources' / 'kotlin-stdlib-native-sources.zip'
    natives = {}
    with zipfile.ZipFile(archive) as z:
        for name in sorted(z.namelist()):
            if not name.endswith('.kt'):
                continue
            lines = z.read(name).decode('utf-8').splitlines()
            owners, depth = [], 0                    # enclosing named classes and objects: (name, brace depth)
            for i, line in enumerate(lines):
                for m in NATIVE.finditer(line):
                    api = kotlin_api(lines, i, [o for o, _ in owners])
                    natives.setdefault(m.group(1), []).append((name.split('/', 1)[1], api))
                code = re.sub(r'"(\\.|[^"\\])*"|//.*', '', line)
                c = re.search(r'\b(?:class|object|interface)\s+(\w+)', code)
                if c and '{' in code:
                    owners.append((c.group(1), depth))
                depth += code.count('{') - code.count('}')
                while owners and depth <= owners[-1][1]:
                    owners.pop()
    return natives


def signature(prefix, params):
    """(return ext, return type, ((ext, type), ...)) of an IR function header; ext is zeroext, signext or ''."""
    def ext(tokens):
        return next((t for t in tokens if t in ('zeroext', 'signext')), '')
    toks = TOKEN.findall(prefix)
    ret = [t for t in toks if TYPE.match(t)]
    out, depth, cur = [], 0, ''
    for ch in params + ',':
        if ch in '<{[(':
            depth += 1
        elif ch in '>}])':
            depth -= 1
        if ch == ',' and depth == 0:
            if cur.strip():
                t = TOKEN.findall(cur)
                out.append((ext(t), next((x for x in t if TYPE.match(x)), '?')))
            cur = ''
        else:
            cur += ch
    return ext(toks), ret[-1] if ret else '?', tuple(out)


def ir_functions(text, kind):
    """{name: signature} of the `define` or `declare` lines of an LLVM IR module (internal ones left out)."""
    funcs = {}
    for m in re.finditer(rf'^{kind}\s+(.*?)@("[^"]+"|[\w.$]+)\((.*?)\)(?=[^)]*$)', text, re.M):
        prefix, name, params = m.groups()
        if kind == 'define' and re.search(r'\b(internal|private)\b', prefix):
            continue
        funcs[name.strip('"')] = signature(prefix, params)
    return funcs


def runtime_functions(tmp):
    """{name: (signature, source file)} of every function runtime/ defines."""
    rt = ROOT / 'runtime'
    flags = [*paths.target_flags(), '-isystem', str(paths.newlib_include()), '-O0', '-fexceptions', '-funwind-tables',
             '-w', '-I', str(rt)]
    defined = {}
    for src in [*sorted(rt.glob('*.c')), *sorted(rt.glob('*.cpp')), *sorted((rt / 'dtoa').glob('*.cpp'))]:
        out = Path(tmp) / (src.name + '.ll')
        cxx = ['-std=c++17', '-fno-rtti'] if src.suffix == '.cpp' else []
        r = subprocess.run([str(paths.clang()), *flags, *cxx, '-S', '-emit-llvm', str(src), '-o', str(out)],
                           capture_output=True, text=True, errors='replace')
        if r.returncode != 0:
            sys.exit(f'clang failed on {src}:\n{r.stderr[-3000:]}')
        for name, sig in ir_functions(out.read_text(errors='replace'), 'define').items():
            defined[name] = (sig, src.name)
    return defined


def library_symbols():
    """Names newlib (libc_nano, libm) and libgcc define: a board link finds these."""
    names = set()
    for lib in (paths.newlib_lib() / 'libc_nano.a', paths.newlib_lib() / 'libm.a', paths.libgcc()):
        r = subprocess.run([str(paths.gcc_bin('nm')), '-g', '--defined-only', str(lib)], capture_output=True,
                           text=True, errors='replace')
        names.update(f[2] for f in (line.split() for line in r.stdout.splitlines()) if len(f) == 3)
    return names


def declared_functions(irs):
    """{name: (signature, file)} of the functions the IR files declare, without LLVM's intrinsics and the C++ ABI.
    A file that declares none stops the run."""
    declared = {}
    for ir in irs:
        funcs = {n: s for n, s in ir_functions(ir.read_text(errors='replace'), 'declare').items()
                 if not n.startswith(('llvm.', '__', '_Z'))}
        if not funcs:
            sys.exit(f'missing_natives: {ir} declares no function: it is not the IR of a compiled Kotlin program')
        for name, sig in funcs.items():
            declared.setdefault(name, (sig, ir))
    return declared


def fmt(sig):
    ret_ext, ret, params = sig
    return f'{(ret_ext + " ") if ret_ext else ""}{ret} ({", ".join((e + " " if e else "") + t for e, t in params)})'


def main():
    args = sys.argv[1:]
    verbose, check = '-v' in args, '--check' in args
    irs = []
    for a in (a for a in args if not a.startswith('-')):
        hits = sorted(glob.glob(a)) if re.search(r'[*?[]', a) else [a]   # PowerShell and cmd leave wildcards to us
        if not hits or not all(Path(h).is_file() for h in hits):
            sys.exit(f'missing_natives: no IR file {a}')
        irs += [Path(h) for h in hits]
    if [a for a in args if a.startswith('-') and a not in ('-v', '--check', '--ir')] or (irs and '--ir' not in args):
        sys.exit(__doc__)
    declared = declared_functions(irs)
    natives = stdlib_natives()
    with tempfile.TemporaryDirectory() as tmp:
        defined = runtime_functions(tmp)

    groups = {'implemented': [], 'unsupported': [], 'Objective-C': [], 'missing': []}
    for name in sorted(natives):
        where = natives[name]
        if name in defined:
            groups['unsupported' if defined[name][1] == UNSUPPORTED_C else 'implemented'].append(name)
        elif OBJC_NAME.search(name) or all(OBJC_FILE.search(f) for f, _ in where):
            groups['Objective-C'].append(name)
        else:
            groups['missing'].append(name)

    print(f'{len(natives)} natives in the Kotlin/Native stdlib: ' +
          ', '.join(f'{len(v)} {k}' for k, v in groups.items()))
    for group, title in (('missing', 'missing (a board link that needs one fails)'),
                         ('unsupported', 'unsupported (runtime/unsupported.c: stops with the Kotlin API name)'),
                         ('Objective-C', 'Objective-C interop (Apple targets only)'), ('implemented', 'implemented')):
        if groups[group] and (verbose or group in ('missing', 'unsupported')):
            print(f'\n{title}:')
            for name in groups[group]:
                file, api = natives[name][0]
                print(f'  {name:60s} {file}: {api}')

    bad = len(groups['missing'])
    if irs:
        libs = library_symbols()
        mismatch = [(n, s, ir) for n, (s, ir) in sorted(declared.items()) if n in defined and defined[n][0] != s]
        absent = [n for n in sorted(declared) if n not in defined and n not in libs and n not in natives and
                  not OBJC_NAME.search(n)]
        print(f'\n{len(declared)} functions declared by {len(irs)} IR file(s): {len(mismatch)} with a signature '
              f'that differs from runtime/, {len(absent)} not defined anywhere (stdlib natives are counted above)')
        for name, sig, ir in mismatch:
            print(f'  {name}\n      {ir.name}: {fmt(sig)}\n      runtime/{defined[name][1]}: {fmt(defined[name][0])}')
        for name in absent:
            print(f'  {name}: not defined')
        bad += len(mismatch) + len(absent)
    sys.exit(1 if check and bad else 0)


if __name__ == '__main__':
    main()
