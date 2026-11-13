"""Extract the cinterop bridges from a kotlinc-native module saved after LinkBitcodeDependencies.

usage: python toolchain/bridges.py out.LinkBitcodeDependencies.ll bridges.ll

A Kotlin call to a C function declared through cinterop goes
    Kotlin --invoke--> _<hash>_<n>_knbridge<k>  --load--> @knifunptr_<pkg>_<fn>_<i> = @<pkg>_<fn>_wrapper<j>
                   --tail call--> <fn>  (the C function, or the body of a static inline one)
and C calls a staticCFunction through
    C --function pointer--> _<hash>_<n>_kncfun<k>  --call--> _<hash>_<n>_knbridge<m>  --> the Kotlin lambda
The Codegen module (what kmicro compiles, out.Codegen.ll next to the input) defines the Kotlin side of each callback
and only declares the other bridges and the C-callable stubs: their bodies, the function-pointer globals and the
wrappers come from the compiler's C stubs, linked in later together with the stock runtime. This tool copies exactly
those pieces and the types they use into a small module, and declares what they reference: the C functions and
globals, and every name Codegen knows (the Kotlin side of a callback comes from k.o, runtime functions from the kmicro
runtime). Full LTO then folds each chain into a direct call. Attribute groups and metadata are dropped (retarget.py
gives the definitions the Cortex-M4 attributes).
"""
import re
import sys
from pathlib import Path

NAME = r'("[^"]*"|[-\w$.]+)'                            # an LLVM name after @ or %: quoted, plain or a number
ROOT = re.compile(r'_kn(bridge|cfun)\d+"?$')
TOKEN = re.compile(r'([@%])' + NAME + r'|"[^"]*"')     # a global, local or type name, or a string (skipped)
LINKAGE = re.compile(r'\b(private|internal|linkonce|linkonce_odr|weak|weak_odr|common|available_externally) ')


def top_level(text):
    """Functions, declarations, globals and types of a module: name -> (position in the file, text)."""
    def find(pattern, flags=re.M):
        return {m.group(1): (m.start(), m.group(0)) for m in re.finditer(pattern, text, flags)}
    return (find(r'^define [^@\n]*@' + NAME + r'\(.*?^}\n', re.M | re.S),
            find(r'^declare [^@\n]*@' + NAME + r'\(.*$'),
            find(r'^@' + NAME + r' = .*$'),
            find(r'^%' + NAME + r' = type .*$'))


def codegen_names(text):
    """The functions a module defines, and every function and global it defines or declares."""
    defined = set(re.findall(r'^define [^@\n]*@' + NAME + r'\(', text, re.M))
    return defined, defined | set(re.findall(r'^declare [^@\n]*@' + NAME + r'\(', text, re.M)) | set(
        re.findall(r'^@' + NAME + ' = ', text, re.M))


def names(text, sigil):
    """The @ (global) or % (local value or type) names used in IR text, outside string constants."""
    return {m.group(2) for m in TOKEN.finditer(text) if m.group(1) == sigil}


def clean(s):
    s = re.sub(r'\s#\d+', '', s)                     # attribute groups (target attributes are stripped anyway)
    s = re.sub(r', !\w+ !\d+', '', s)                # !tbaa etc.
    s = re.sub(r' !\w+ !\d+', '', s)
    return s


def function_declaration(define):
    """`define [linkage] <ret> @f(<params>) <attributes> {...}` -> `declare <ret> @f(<params>)`."""
    head = define.split('\n', 1)[0]
    m = re.match(r'define ([^@]*)@' + NAME + r'\(', head)
    i, depth = m.end(), 1
    while depth:                                        # to the parenthesis that closes the parameter list
        depth += (head[i] == '(') - (head[i] == ')')
        i += 1
    return 'declare ' + LINKAGE.sub('', m.group(1)) + head[m.start(2) - 1:i]


def global_declaration(name, line):
    """`@g = [linkage] global|constant <type> <initializer>` -> `@g = external global <type>`."""
    m = re.match(r'@' + NAME + r' = (?:[\w()]+ )*?(?:global|constant) ', line)
    rest, depth, i = line[m.end():], 0, 0
    while i < len(rest) and (depth or rest[i] not in ' ,'):
        depth += (rest[i] in '{[<(') - (rest[i] in '}]>)')
        i += 1
    return f'@{name} = external global {rest[:i]}'


def extract(lbd, codegen):
    """The bridges module (IR text) and a one-line summary, from the LinkBitcodeDependencies and Codegen IR."""
    defs, decls, globs, types = top_level(lbd)
    k_defs, kotlin = codegen_names(codegen)            # k.o and the kmicro runtime provide these
    roots = [n for n in defs if ROOT.search(n) and n not in k_defs]
    out_defs, out_globs, out_decls, seen, want = {}, {}, {}, set(), list(roots)
    while want:
        n = want.pop()
        if n in seen or n.startswith('llvm.'):
            continue
        seen.add(n)
        if n in kotlin and n not in roots:              # declared, never copied: no Kotlin or runtime code here
            if n in decls:
                out_decls[n] = decls[n]
            elif n in defs:
                out_decls[n] = (defs[n][0], function_declaration(defs[n][1]))
            elif n in globs:
                out_globs[n] = (globs[n][0], global_declaration(n, globs[n][1]))
            continue
        if n in decls:
            out_decls[n] = decls[n]
            continue
        piece = defs.get(n) or globs.get(n)
        if piece:
            (out_defs if n in defs else out_globs)[n] = piece
            want += names(clean(piece[1]), '@') - {n}
    pieces = [clean(t) for d in (out_globs, out_decls, out_defs) for _, t in d.values()]
    used, todo = set(), set().union(*(names(p, '%') for p in pieces)) & set(types)
    # the struct types, and the types inside them (a local %0 also brings a numbered type %0 along: unused, harmless)
    while todo:
        t = todo.pop()
        used.add(t)
        todo |= (names(types[t][1], '%') & set(types)) - used

    def ordered(d):                                     # numbered names (@0, %3) must keep increasing in the file
        return [clean(t) for _, t in sorted(d.values())]
    header = [l for l in lbd.splitlines() if l.startswith(('target datalayout', 'target triple'))]
    text = '\n'.join(['; cinterop bridges extracted by kmicro toolchain/bridges.py', *header, '',
                      *ordered({t: types[t] for t in used}), '', *ordered(out_globs), '',
                      *ordered({**out_decls, **out_defs})]) + '\n'
    calls_c = sorted(n for n in out_decls if n not in kotlin)
    summary = (f'bridges: {sum("knbridge" in n for n in roots)} Kotlin->C bridges, '
               f'{sum("kncfun" in n for n in roots)} C->Kotlin stubs; copied {len(out_defs)} functions, '
               f'{len(out_globs)} pointers, {len(used)} types; C functions: ' + ' '.join(calls_c))
    return text, summary


def main():
    lbd, dst = Path(sys.argv[1]), Path(sys.argv[2])
    text, summary = extract(lbd.read_text(encoding='utf-8'),
                            lbd.with_name('out.Codegen.ll').read_text(encoding='utf-8'))
    dst.write_text(text, encoding='utf-8', newline='\n')
    print(summary)


if __name__ == '__main__':
    main()
