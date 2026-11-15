# Copyright 2026 the kmicro authors (NOTICE).
# SPDX-License-Identifier: Apache-2.0
"""Struct results between Kotlin and C on a core without an FPU.

kotlinc-native and cinterop compile for linux_arm32_hfp, the hard-float ABI. There a C function that returns a struct
of floating-point numbers (two to four floats, one to four doubles) returns it in registers, and clang writes the call
in the IR that way: `%r = call %struct.vec2 @vec_make(float, float)`. The backend chooses the convention later, from
the core, for scalars only. The base ABI of a core without an FPU returns every struct larger than 4 bytes in memory,
through a pointer the caller passes first, and the C side, compiled for that core, does so. Left alone, the two
sides disagree: the C function writes its result to the address in r0, which holds the first argument.

in_memory() rewrites a module of cinterop bridges for such a core:

- a C function declared with a struct result gets the pointer as its first parameter (`sret`), and each call of it
  passes a slot of its own and loads the result from there;
- a callback Kotlin gives to C (`staticCFunction`, the functions named `..._kncfunN`) that returns such a struct
  takes that pointer too, and stores its result there.

Calls between the bridges themselves keep the form the compiler gave them: both ends are code of this module. Struct
arguments need no change: the two conventions put them in the same registers.
"""
import re

AGGREGATE = r'(?:%[\w.$-]+|%"[^"]+"|\{[^@()]*\}|\[[^@()]*\])'
NAME = r'(?:"[^"]+"|[\w.$-]+)'
ATTRS = r'(?:[a-z_]+(?:\([^()]*\))? )*?'
TYPE_DEF = re.compile(rf'^(%[\w.$-]+|%"[^"]+") = type (.+)$', re.M)
DECLARE = re.compile(rf'^declare (?P<pre>{ATTRS})(?P<ret>{AGGREGATE}) @(?P<name>{NAME})'
                     r'\((?P<args>.*)\)(?P<rest>[^()]*)$', re.M)
CALLBACK = re.compile(rf'^define (?P<pre>{ATTRS})(?P<ret>{AGGREGATE}) @(?P<name>"?[\w.$-]*_kncfun\d+"?)'
                      r'\((?P<args>.*)\)(?P<rest>[^(){]*)\{$')
CALL = (r'^(?P<ind>\s*)(?:(?P<res>%[\w.$-]+) = )?(?:tail |notail |musttail )?call (?P<pre>{attrs})(?P<ret>{ret}) '
        r'{callee}\((?P<args>.*)\)(?P<rest>[^()]*)$')
SCALARS = {'float': (4, 4), 'double': (8, 8), 'ptr': (4, 4), 'i1': (1, 1), 'i8': (1, 1), 'i16': (2, 2), 'i32': (4, 4),
           'i64': (8, 8)}


def fields(body):
    """The members of `{ a, b }`'s body or of an argument list, split at the commas outside brackets."""
    out, depth, cur = [], 0, ''
    for ch in body:
        depth += ch in '{[(<'
        depth -= ch in '}])>'
        if ch == ',' and depth == 0:
            out.append(cur.strip())
            cur = ''
        else:
            cur += ch
    return [*out, cur.strip()] if cur.strip() else out


def layout(t, types, depth=0):
    """(size, alignment) of an IR type as the C compiler lays it out on a 32-bit ARM core. ValueError for a type
    this module does not know (a packed struct, a vector, an opaque type)."""
    t = t.strip()
    if depth > 20:
        raise ValueError(t)
    if t in SCALARS:
        return SCALARS[t]
    if t in types:
        return layout(types[t], types, depth + 1)
    array = re.fullmatch(r'\[(\d+) x (.+)\]', t)
    if array:
        size, align = layout(array.group(2), types, depth + 1)
        return int(array.group(1)) * size, align
    if t.startswith('{') and t.endswith('}'):
        off, most = 0, 1
        for f in fields(t[1:-1]):
            size, align = layout(f, types, depth + 1)
            off = (off + align - 1) // align * align + size
            most = max(most, align)
        return (off + most - 1) // most * most, most
    raise ValueError(t)


def in_memory(text):
    """The module with struct results of C functions and of callbacks passed in memory (see the module docstring).
    Raises ValueError, with a message for the user, for a shape it does not handle."""
    types = dict(TYPE_DEF.findall(text))

    def slot(ret, what):
        try:
            size, align = layout(ret, types)
        except ValueError:
            raise ValueError(f'{what} returns {ret}, a type whose layout is not known here') from None
        if size <= 4:       # returned in r0 by the base ABI; a struct of one float is all that gets here
            raise ValueError(f'{what} returns a struct of {size} bytes by value, which kmicro cannot pass on a core '
                             'without an FPU: return it through a pointer parameter')
        return f'ptr sret({ret}) align {align}', align

    def with_first(first, args):
        return first + (', ' + args if args.strip() else '')

    c_functions = {}
    for m in DECLARE.finditer(text):
        if not m['name'].startswith('llvm.'):
            c_functions[m['name']] = slot(m['ret'], f'the C function {m["name"]}')

    def declare(m):
        if m['name'] not in c_functions:
            return m[0]
        return f'declare {m["pre"]}void @{m["name"]}({with_first(c_functions[m["name"]][0], m["args"])}){m["rest"]}'
    text = DECLARE.sub(declare, text)

    out, callback, loaded = [], None, set()
    direct = re.compile(CALL.format(attrs=ATTRS, ret=AGGREGATE, callee=rf'@(?P<name>{NAME})'))
    indirect = re.compile(CALL.format(attrs=ATTRS, ret=AGGREGATE, callee=r'(?P<reg>%[\w.$-]+)'))
    for line in text.split('\n'):
        if line.startswith('define '):
            loaded = set()                          # the registers of this function that hold a bridge's address
            m = CALLBACK.match(line)
            callback = None
            if m:
                param, align = slot(m['ret'], 'a callback that Kotlin gives to C (staticCFunction)')
                callback = (m['ret'], align)
                line = (f'define {m["pre"]}void @{m["name"]}({with_first(param + " %kmicro.result", m["args"])})'
                        f'{m["rest"]}{{')
        elif line == '}':
            callback = None
        elif callback and re.fullmatch(rf'\s*ret {re.escape(callback[0])} .+', line):
            value = line.strip()[len('ret '):]
            out.append(f'  store {value}, ptr %kmicro.result, align {callback[1]}')
            line = '  ret void'
        else:
            m = re.match(r'\s*(%[\w.$-]+) = load ptr, ptr @knifunptr_', line)
            if m:
                loaded.add(m[1])
            m = direct.match(line)
            if m and m['name'] in c_functions:
                param, align = c_functions[m['name']]
                mem = '%kmicro.result.' + (m['res'] or '%' + str(len(out)))[1:]
                out.append(f'{m["ind"]}{mem} = alloca {m["ret"]}, align {align}')
                out.append(f'{m["ind"]}call {m["pre"]}void @{m["name"]}({with_first(param + " " + mem, m["args"])})'
                           f'{m["rest"]}')
                # (a result without a name still has a number: the load takes it, and the numbers after it stay)
                into = m['res'] + ' = ' if m['res'] else ''
                line = f'{m["ind"]}{into}load {m["ret"]}, ptr {mem}, align {align}'
            elif m and re.search(r'_kncfun\d+"?$', m['name']):
                raise ValueError(f'a bridge calls the callback {m["name"]}, which returns a struct, by name')
            m = indirect.match(line)
            if m and m['reg'] not in loaded:
                raise ValueError('a call through a C function pointer returns a struct of floating-point numbers '
                                 'by value, which kmicro cannot pass on a core without an FPU: call a C function '
                                 'that returns it through a pointer parameter')
        out.append(line)
    return '\n'.join(out)
