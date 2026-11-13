"""Retarget a probe's Codegen IR to Cortex-M4, link it with full LTO + --gc-sections against trapping stubs, and report
(1) the flash/RAM the Kotlin side really costs and (2) the runtime symbols that survive dead-code elimination.

usage: python measure.py <probe-dir> <name> <kfun-prefix> [<kfun-prefix> ...]
  kfun-prefix: e.g. 'kfun:#entry(' -- every defined IR function whose name starts with it is kept as a root.
"""
import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'toolchain'))
import paths  # noqa: E402

T = paths.TARGET_M4F
TOOLS = Path(__file__).resolve().parent.parent / 'toolchain'


def sh(args, **kw):
    r = subprocess.run([str(a) for a in args], capture_output=True, text=True, **kw)
    if r.returncode != 0:
        sys.exit(f'FAILED: {" ".join(map(str, args))[:300]}\n{r.stderr[-3000:]}')
    return r.stdout


def main():
    d, name, prefixes = Path(sys.argv[1]), sys.argv[2], sys.argv[3:]
    src = d / f'ir_{name}' / 'out.Codegen.ll'
    out = d / f'm_{name}'
    out.mkdir(exist_ok=True)
    ll, stubs = out / 'm4.ll', out / 'stubs.c'
    sh([sys.executable, TOOLS / 'retarget.py', src, ll, '--stubs', stubs, '--no-tls', '--eh-stubs'])
    text = ll.read_text(encoding='utf-8')
    roots = [m.group(1) for m in re.finditer(r'^define [^@]*@"(kfun:[^"]+)"\(', text, re.M)
             if any(m.group(1).startswith(p) for p in prefixes)]
    if not roots:
        sys.exit('no roots found')
    stub_names = set(re.findall(r'void (\S+)\(void\)', stubs.read_text()))
    sh([paths.clang(), *T, '-O2', '-flto', '-c', '-x', 'ir', ll, '-o', out / 'k.o'])
    sh([paths.clang(), *T, '-O2', '-ffunction-sections', '-w', '-c', stubs, '-o', out / 'stubs.o'])
    elf = out / 'p.elf'
    sh([paths.ld_lld(), f'--entry={roots[0]}', *[f'--undefined={r}' for r in roots[1:]], '--gc-sections',
        '-Ttext=0x08000000', '--lto-O2', '-o', elf, out / 'k.o', out / 'stubs.o', f'-L{paths.newlib_lib()}', '-lc_nano', '-lnosys', paths.libgcc()])
    sizes = {}
    for line in sh([paths.gcc_bin('size'), '-A', elf]).splitlines():
        p = line.split()
        if len(p) == 3 and p[1].isdigit() and int(p[1]) > 0 and not p[0].startswith(('.comment', '.ARM.attr', '.debug', '.relro')):
            sizes[p[0]] = int(p[1])
    syms = sh([paths.gcc_bin('nm'), '-S', '--size-sort', elf])
    kept_stubs, kotlin_bytes = [], 0
    for line in syms.splitlines():
        p = line.split(maxsplit=3)
        if len(p) == 4:
            if p[3] in stub_names:
                kept_stubs.append(p[3])
            elif p[2] in 'tTwW':
                kotlin_bytes += int(p[1], 16)
    res = {'probe': name, 'roots': roots, 'sections': sizes, 'code_bytes_excluding_stubs': kotlin_bytes,
           'runtime_symbols_needed': sorted(kept_stubs)}
    (out / 'result.json').write_text(json.dumps(res, indent=1))
    print(json.dumps({k: v for k, v in res.items() if k != 'runtime_symbols_needed'}))
    print(f'runtime symbols needed ({len(kept_stubs)}):', ' '.join(sorted(kept_stubs)))


if __name__ == '__main__':
    main()
