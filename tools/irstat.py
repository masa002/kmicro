"""Quick statistics over a textual LLVM IR module (.ll) produced by kotlinc-native -Xsave-llvm-ir-after.

usage: python tools/irstat.py MODULE [--list-decls] [--list-defs]

    MODULE        a .ll file, or a tools/kbuild.py (or run_all) output folder: its ir/out.Codegen.ll
    --list-decls  also list every declared function (LLVM intrinsics included)
    --list-defs   also list every defined function

Reports: defined / declared functions, external symbols the module needs (the runtime contract), thread_local
globals, 64-bit atomics, EH constructs (invoke / landingpad / personality), target-cpu / target-features attributes,
and the instruction count per defined function (top 25).
"""
import argparse
import re
import sys
from collections import Counter
from pathlib import Path

DEF_RE = re.compile(r'^define\s+(?:[^@]*?)@("?[^"(\s]+"?)\(')
DECL_RE = re.compile(r'^declare\s+(?:[^@]*?)@("?[^"(\s]+"?)\(')
GLOBAL_RE = re.compile(r'^@("?[^"=\s]+"?)\s*=\s*(.*)$')
ATTR_RE = re.compile(r'^attributes #(\d+) = \{(.*)\}')
LANDINGPAD_RE = re.compile(r'^(?:%\S+ = )?landingpad\b')


def main():
    ap = argparse.ArgumentParser(usage='python tools/irstat.py MODULE [--list-decls] [--list-defs]',
                                 description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('module', type=Path, help=argparse.SUPPRESS)
    ap.add_argument('--list-decls', action='store_true', help=argparse.SUPPRESS)
    ap.add_argument('--list-defs', action='store_true', help=argparse.SUPPRESS)
    args = ap.parse_args()
    path = args.module / 'ir/out.Codegen.ll' if args.module.is_dir() else args.module
    if not path.is_file():
        sys.exit(f'irstat: no such module: {path}')
    defs, decls = [], []
    sizes = Counter()
    tls, globals_ext, globals_def = [], [], 0
    eh = Counter()
    atomics64 = Counter()
    attrs = {}
    cur = None
    with open(path, encoding='utf-8', errors='replace') as f:
        for line in f:
            if line.startswith('define '):
                m = DEF_RE.match(line)
                cur = m.group(1) if m else '?'
                defs.append(cur)
                if 'personality' in line:
                    eh['personality'] += 1
                continue
            if line.startswith('}'):
                cur = None
                continue
            if cur is not None:
                s = line.strip()
                if s and not s.endswith(':') and not s.startswith(';'):
                    sizes[cur] += 1
                if ' invoke ' in s or s.startswith('invoke ') or '= invoke ' in s:
                    eh['invoke'] += 1
                if LANDINGPAD_RE.match(s):          # the instruction, not `unwind label %landingpad...`
                    eh['landingpad'] += 1
                if ('atomicrmw' in s or 'cmpxchg' in s or ' atomic ' in s) and 'i64' in s:
                    atomics64[s.split()[2] if '=' in s else s.split()[0]] += 1
                continue
            if line.startswith('declare '):
                m = DECL_RE.match(line)
                decls.append(m.group(1) if m else line.strip())
                continue
            m = GLOBAL_RE.match(line)
            if m:
                name, rest = m.groups()
                if 'thread_local' in rest:
                    tls.append(name)
                if rest.startswith('external ') or ' external ' in rest.split('=')[0]:
                    globals_ext.append(name)
                else:
                    globals_def += 1
                continue
            m = ATTR_RE.match(line)
            if m:
                attrs[m.group(1)] = m.group(2)

    cpu = Counter(re.search(r'"target-cpu"="([^"]*)"', a).group(1) for a in attrs.values()
                  if '"target-cpu"' in a)
    feats = Counter(re.search(r'"target-features"="([^"]*)"', a).group(1)[:80] for a in attrs.values()
                    if '"target-features"' in a)
    intrinsics = [d for d in decls if d.startswith('llvm.') or d.startswith('"llvm.')]
    runtime = sorted(d for d in decls if d not in intrinsics)
    print(f'file: {path}')
    print(f'defined functions: {len(defs)}   instructions: {sum(sizes.values())}')
    print(f'declared functions: {len(decls)} (llvm intrinsics {len(intrinsics)}, external {len(runtime)})')
    print(f'external globals: {len(globals_ext)}   defined globals: {globals_def}   thread_local: {len(tls)}')
    print(f'EH: {dict(eh)}   64-bit atomics: {dict(atomics64)}')
    print(f'target-cpu: {dict(cpu)}')
    print(f'target-features (first 80 chars): {dict(feats)}')
    if tls:
        print('thread_local globals:', ', '.join(tls[:20]))
    print('\nexternal functions (the runtime contract):')
    for d in runtime:
        print('  ', d)
    if globals_ext:
        print('\nexternal globals:')
        for g in globals_ext:
            print('  ', g)
    print('\nlargest defined functions:')
    for name, n in sizes.most_common(25):
        print(f'  {n:6d}  {name}')
    if args.list_decls:
        print('\nall declared functions:')
        for d in decls:
            print('  ', d)
    if args.list_defs:
        print('\nall defined functions:')
        for d in defs:
            print('  ', d)


if __name__ == '__main__':
    main()
