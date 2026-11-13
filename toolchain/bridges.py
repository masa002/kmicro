"""Extract the cinterop call bridges from a kotlinc-native module saved after LinkBitcodeDependencies.

usage: python bridges.py out.LinkBitcodeDependencies.ll bridges.ll

A Kotlin call to a C function declared through cinterop goes
    Kotlin --invoke--> _<hash>_<n>_knbridge<k>  --load--> @knifunptr_<pkg>_<fn>_<i> = @<pkg>_<fn>_wrapper<j>
                   --tail call--> <fn>  (the C kernel function)
The Codegen module (what kmicro compiles) only declares the knbridge functions; their bodies, the function-pointer
globals and the wrappers come from the compiler's C stubs, linked in later together with the stock runtime. This
tool copies exactly those pieces (and the declarations of the C functions they call) into a small module. Full LTO
then folds the chain into a direct call. Attribute groups, metadata and personality-free bodies are kept minimal.
"""
import re
import sys

src, dst = sys.argv[1], sys.argv[2]
text = open(src, encoding='utf-8').read()

header = []
for line in text.splitlines():
    if line.startswith(('target datalayout', 'target triple')):
        header.append(line)

defs = {m.group(1): m.group(0) for m in re.finditer(r'^define [^@]*@("?[^"(\s]+"?)\(.*?^}\n', text, re.M | re.S)}
decls = {m.group(1): m.group(0) for m in re.finditer(r'^declare [^@]*@("?[^"(\s]+"?)\(.*$', text, re.M)}
globs = {m.group(1): m.group(0) for m in re.finditer(r'^@("?[^"=\s]+"?) = .*$', text, re.M)}

want = [n for n in defs if re.search(r'_knbridge\d+"?$', n)]
out_defs, out_globs, out_decls, seen = [], [], [], set()
while want:
    n = want.pop()
    if n in seen:
        continue
    seen.add(n)
    if n in defs:
        body = defs[n]
        out_defs.append(body)
    elif n in globs:
        body = globs[n]
        out_globs.append(body)
    elif n in decls:
        out_decls.append(decls[n])
        continue
    else:
        continue
    for ref in re.findall(r'@("?[A-Za-z_$.][^"\s(),]*"?)', body):
        if ref != n and not ref.startswith('llvm.'):
            want.append(ref)


def clean(s):
    s = re.sub(r'\s#\d+', '', s)                     # attribute groups (target attributes are stripped anyway)
    s = re.sub(r', !\w+ !\d+', '', s)                # !tbaa etc.
    s = re.sub(r' !\w+ !\d+', '', s)
    return s


with open(dst, 'w', encoding='utf-8', newline='\n') as f:
    f.write('; cinterop bridges extracted by kmicro toolchain/bridges.py\n')
    f.write('\n'.join(header) + '\n\n')
    for g in sorted(out_globs):
        f.write(clean(g) + '\n')
    f.write('\n')
    for d in sorted(out_decls):
        f.write(clean(d) + '\n')
    f.write('\n')
    for d in out_defs:
        f.write(clean(d) + '\n')
print(f'bridges: {sum(1 for d in out_defs if "knbridge" in d.split("(")[0])} bridges, {len(out_globs)} pointers, '
      f'{len(out_defs)} functions, {len(out_decls)} C functions: '
      + ' '.join(re.search(r'@("?[^"(\s]+"?)\(', d).group(1) for d in sorted(out_decls)))
