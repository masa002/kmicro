#!/usr/bin/env python3
# Copyright 2026 the kmicro authors (NOTICE).
# SPDX-License-Identifier: Apache-2.0
"""Generate Kotlin register constants from CMSIS headers: every register address and every bit constant.

    python tools/gen_regs.py --header core_cm4.h --header stm32l431xx.h [--pins board.h] --sources kotlin/
                             --out kotlin/Regs.kt --package NAME [--all]

Nothing is typed by hand: addresses come from the CMSIS struct layouts (offsets computed here) and the instance
macros (`#define RCC ((RCC_TypeDef *) RCC_BASE)`); bit constants from the `#define X_Pos / X_Msk / X` macros.
Registers are `object RCC { const val CR: UInt = 0x40021000u ... }`: reading RCC.CR is a compile-time constant
(the object is never created). Kotlin reads and writes them through hw_rd32 / hw_wr32 (support/hw.h). With
--sources only the names the Kotlin files in that folder and its subfolders use are emitted (the full set is 13,000
lines and slow to compile), and a warning names each of them that the headers define but that is left out, with the
reason: a struct with a union or a bit field, a macro or an interrupt number that is no integer constant, or one
that a header defines twice with different values (under `#if` and again under `#else`).
examples/irq shows the whole flow.
"""
import re
import sys
from pathlib import Path

SIZES = {'uint32_t': 4, 'uint16_t': 2, 'uint8_t': 1, 'int32_t': 4, 'int16_t': 2, 'int8_t': 1}
TWICE = 'the header gives it more than one value, a preprocessor condition decides which'


def strip_comments(s):
    """s without its comments. A comment's line ends stay, so that line numbers do."""
    return re.sub(r'/\*.*?\*/|//[^\n]*', lambda m: '\n' * m.group(0).count('\n'), s, flags=re.S)


def layout(body, defines, types):
    """The body of a struct -> ([(field, offset, size, count)], the struct's size, its alignment), laid out as the C
    compiler does: a member at a multiple of its alignment, the struct as aligned as its most aligned member and its
    size a multiple of that. Raises ValueError for what is no plain register layout: a union, a bit field, a pointer,
    an unknown type, an array size that is no constant."""
    fields, off, most = [], 0, 1
    for decl in body.split(';'):
        decl = re.sub(r'\b(__IO|__I|__O|__IM|__OM|__IOM|volatile|const)\b', ' ', decl).strip()
        if not decl:
            continue
        d = re.match(r'(\w+)\s+(.+)$', decl, re.S)
        if d and d.group(1) in SIZES:
            size = align = SIZES[d.group(1)]
        elif d and d.group(1) in types:                 # a struct of registers: 3 bytes stay 3 bytes
            size, align = types[d.group(1)][1:]
        else:
            raise ValueError(decl)
        most = max(most, align)
        for item in d.group(2).split(','):              # `uint32_t CR1, CR2;` declares two registers
            f = re.fullmatch(r'\s*(\w+)\s*(?:\[([^\]]+)\])?\s*', item)
            if not f:
                raise ValueError(decl)
            off = (off + align - 1) // align * align
            count = evaluate(f.group(2), defines) if f.group(2) else 1
            fields.append((f.group(1), off, size, count))
            off += size * count
    return fields, (off + most - 1) // most * most, most


def parse(text, header, defines, types, instances, irqs, where, unknown):
    """Adds what the header defines to the tables. where: a macro, a struct or an interrupt number -> 'header line N',
    and for a struct that is not understood also the declaration that is the reason. unknown: a macro or an interrupt
    number without a value -> the reason."""
    texts = {}                                          # the macros of this header -> their text, None for two texts
    for n, line in enumerate(text.splitlines(), 1):     # the macros first: a struct may size an array with one
        d = re.match(r'\s*#define\s+(\w+)\s+(.+?)\s*$', line)
        if not d:
            continue
        name, val = d.group(1), d.group(2)
        where[name] = f'{header} line {n}'
        defines.pop(name, None)                         # a later header defines it anew
        instances.pop(name, None)
        unknown.pop(name, None)
        if texts.setdefault(name, val) != val:          # the name once more, as under `#if` and again under `#else`
            texts[name], unknown[name] = None, TWICE    # what is computed from it is left out too
            continue
        inst = re.match(r'\(\(\s*(\w+)\s*\*\s*\)\s*(\w+)\s*\)$', val)
        if inst:
            instances[name] = (inst.group(1), inst.group(2))
        elif '(' not in name:
            defines[name] = val
    enumerators(text, header, defines, irqs, where, unknown)
    # A body may hold a union or a struct in braces. It is not understood then, but reported under its own name.
    for m in re.finditer(r'typedef\s+struct\s*\w*\s*\{((?:[^{}]|\{[^{}]*\})*)\}\s*(\w+)\s*;', text):
        n = text.count('\n', 0, m.start()) + 1
        where[m.group(2)] = f'{header} line {n}'
        try:
            types[m.group(2)] = layout(m.group(1), defines, types)
        except ValueError as e:                         # its instances are left out
            where[m.group(2)] += ': ' + ' '.join(str(e).split())


CASTS = {'uint32_t': (32, False), 'int32_t': (32, True), 'uint16_t': (16, False), 'int16_t': (16, True),
         'uint8_t': (8, False), 'int8_t': (8, True)}
TOKEN = re.compile(r'\s*(?:(0[xX][0-9A-Fa-f]+|\d+)([uUlL]*)(?![\w.])|([A-Za-z_]\w*)|(<<|>>|[()+\-*/%|&^~]))')
LEVELS = [('|',), ('^',), ('&',), ('<<', '>>'), ('+', '-'), ('*', '/', '%')]      # loosest first


def wrap(v, unsigned, bits=32):
    """v in that many bits: 0 .. 2^bits-1 when unsigned, -2^(bits-1) .. 2^(bits-1)-1 otherwise."""
    v &= (1 << bits) - 1
    return v if unsigned or not v >> (bits - 1) else v - (1 << bits)


def tokens(expr, defines, depth=0):
    """The tokens of expr, a macro's name replaced by the tokens of its text as the preprocessor does: with
    `#define A 1 + 2`, `A * 3` is `1 + 2 * 3`. Raises ValueError for what is no token here."""
    if depth > 40:
        raise ValueError(expr)
    out, pos = [], 0
    while expr[pos:].strip():
        m = TOKEN.match(expr, pos)
        if not m:
            raise ValueError(expr)
        pos = m.end()
        if m.group(3) in defines:
            out += tokens(defines[m.group(3)], defines, depth + 1)
        else:
            out.append(m.groups())
    return out


def value(expr, defines):
    """(the value, whether its type is unsigned, the bits of its type) of a C integer constant expression, computed
    as a compiler with a 32-bit int and long and a 64-bit long long does: `~0UL >> 4` is 0x0FFFFFFF, `~0ULL >> 4` has
    60 bits, `-7 / 2` is -3, `(uint8_t)0x1FF` is 255. Raises ValueError for anything else: an unknown name, a
    floating-point number, a number that needs more than 64 bits, an operator other than + - * / % << >> | & ^ ~."""
    toks, at = tokens(expr, defines), 0

    def peek():
        return toks[at][3] if at < len(toks) else None

    def unary():
        nonlocal at
        if at >= len(toks):
            raise ValueError(expr)
        number, suffix, name, op = toks[at]
        at += 1
        if number:
            octal = number[0] == '0' and number[1:].isdigit()                  # C's octal: 017 (08 is no number)
            v, suffix = int(number, 8 if octal else 0), suffix.lower()
            # The first type that holds the number. Only `u` makes a decimal one unsigned: 2147483648 is a long long.
            decimal = number[0] != '0'
            for bits in (64,) if 'll' in suffix else (32, 64):
                for unsigned in (True,) if 'u' in suffix else (False,) if decimal else (False, True):
                    if not v >> (bits if unsigned else bits - 1):
                        return v, unsigned, bits
            raise ValueError(expr)
        if name:
            raise ValueError(name)
        if op in ('+', '-', '~'):
            v, unsigned, bits = unary()
            return wrap({'+': v, '-': -v, '~': ~v}[op], unsigned, bits), unsigned, bits
        if op != '(':
            raise ValueError(expr)
        cast = at + 1 < len(toks) and toks[at][2] in CASTS and toks[at + 1][3] == ')' and CASTS[toks[at][2]]
        if cast:
            at += 2
            bits, signed = cast
            v = unary()[0] & ((1 << bits) - 1)
            if signed and v >> (bits - 1):
                v -= 1 << bits
            return v, bits == 32 and not signed, 32     # a narrower type is promoted to int
        r = binary(0)
        if peek() != ')':
            raise ValueError(expr)
        at += 1
        return r

    def binary(level):
        nonlocal at
        if level == len(LEVELS):
            return unary()
        x, xu, xb = binary(level + 1)
        while peek() in LEVELS[level]:
            op = peek()
            at += 1
            y, yu, yb = binary(level + 1)
            if op in ('<<', '>>'):                      # the result has the type of the left side
                if not 0 <= y < xb:
                    raise ValueError(expr)
                x = wrap(x << y if op == '<<' else x >> y, xu, xb)
                continue
            # The wider type wins; of two types of one width, the unsigned one.
            xu, xb = (xu and xb >= yb) or (yu and yb >= xb), max(xb, yb)
            x, y = wrap(x, xu, xb), wrap(y, xu, xb)
            if op in ('/', '%'):
                if y == 0:
                    raise ValueError(expr)
                q = abs(x) // abs(y) * (-1 if (x < 0) != (y < 0) else 1)       # C rounds towards zero
                x = q if op == '/' else x - q * y
            else:
                x = {'|': x | y, '^': x ^ y, '&': x & y, '+': x + y, '-': x - y, '*': x * y}[op]
            x = wrap(x, xu, xb)
        return x, xu, xb

    r = binary(0)
    if at != len(toks):
        raise ValueError(expr)
    return r


def evaluate(expr, defines):
    """The value of a C integer constant expression as 32 bits (see value()). Raises ValueError also for a long long
    value that neither int nor unsigned int holds."""
    v = value(expr, defines)[0]
    if not -0x80000000 <= v <= 0xFFFFFFFF:
        raise ValueError(expr)
    return v & 0xFFFFFFFF


def enumerators(text, header, defines, irqs, where, unknown):
    """The `NAME_IRQn` enumerators of the header's enums -> irqs, with the values C gives them: the constant after
    `=`, or one more than the enumerator before. unknown: an enumerator without a value here -> the reason."""
    seen = {}                                           # every enumerator of the header -> its value, or None
    for m in re.finditer(r'\benum\b\s*\w*\s*\{([^{}]*)\}', text):
        known, nxt, gap = {}, 0, ''                     # known: this enum's names so far, for `B = A + 1`
        for item in re.finditer(r'[^,]+', m.group(1)):
            body = item.group(0)
            if re.search(r'^\s*#', body, re.M):         # `#if` inside the enum: which enumerators exist is not known
                body, nxt = re.sub(r'^\s*#[^\n]*', lambda d: ' ' * len(d.group(0)), body, flags=re.M), None
                gap = 'a preprocessor condition inside the enum decides its value'
            e = re.fullmatch(r'\s*(\w+)\s*(?:=(.+))?\s*', body, re.S)
            if not e:
                nxt, gap = None, 'its value follows from an enumerator that is not understood'
                continue
            name, why = e.group(1), None
            line = text.count('\n', 0, m.start(1) + item.start() + e.start(1)) + 1
            if e.group(2):
                try:
                    nxt = value(e.group(2), {**defines, **known})[0]
                    nxt = wrap(nxt, False)              # an enumerator is an int
                except ValueError:
                    nxt, why = None, f'{" ".join(e.group(2).split())} is no integer constant'
                    gap = 'its value follows from an enumerator that is not understood'
            elif nxt is None:
                why = gap
            v = nxt
            if seen.setdefault(name, v) != v:           # the name once more, as under `#if` and again under `#else`
                v, why = None, TWICE
            seen[name] = v
            if name.endswith('_IRQn'):
                where[name] = f'{header} line {line}'
                irqs.pop(name, None)
                unknown.pop(name, None)
                if v is None:
                    unknown[name] = why
                else:
                    irqs[name] = v
            known.pop(name, None)
            if v is not None:
                known[name] = str(v)
            if nxt is not None:
                nxt += 1


def used_names(sources, out):
    names = set()
    for f in sorted(Path(sources).rglob('*.kt')):
        text = f.read_text(encoding='utf-8')
        if f.resolve() == Path(out).resolve() or re.match(r'// Generated by (kmicro )?\S*gen_regs\.py', text):
            continue                                    # a generated file names everything it holds
        code = re.sub(r'//[^\n]*|/\*.*?\*/', '', text, flags=re.S)
        names |= set(re.findall(r'\b[A-Za-z_][A-Za-z0-9_]*\b', code))
    return names


def main():
    import argparse
    ap = argparse.ArgumentParser(description='CMSIS headers -> Kotlin register constants (see the module docstring)')
    ap.add_argument('--header', action='append', required=True, type=Path,
                    help='a CMSIS header, in include order (core_cm4.h first, then the device header)')
    ap.add_argument('--pins', type=Path, help='a board header with `#define NAME_PORT GPIOx` / `#define NAME_PIN n`')
    ap.add_argument('--sources', type=Path,
                    help='the Kotlin sources folder (with its subfolders): only the names they use are emitted')
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--package', required=True, help='the Kotlin package of the generated file')
    ap.add_argument('--all', action='store_true', help='every register and constant (slow to compile)')
    a = ap.parse_args()
    for f in [*a.header, *([a.pins] if a.pins else [])]:
        if not f.is_file():
            ap.error(f'{f}: no such file')
    if a.sources and not a.sources.is_dir():
        ap.error(f'--sources {a.sources}: no such folder')
    used = None if a.all or not a.sources else used_names(a.sources, a.out)
    defines, types, instances, irqs, where, unknown = {}, {}, {}, {}, {}, {}
    for h in a.header:
        parse(strip_comments(h.read_text(encoding='utf-8', errors='replace')), h.name, defines, types, instances, irqs,
              where, unknown)
    # a name that is wanted -> why it is not in the file
    left_out = {name: f'{why}, at {where[name]}' for name, why in unknown.items() if used is None or name in used}
    srcs = ', '.join(h.name for h in a.header) + (f' and {a.pins.name}' if a.pins else '')
    out = [f'// Generated by kmicro tools/gen_regs.py from {srcs}. Do not edit.',
           '@file:Suppress("unused", "ObjectPropertyName", "ClassName", "SpellCheckingInspection")',
           '', f'package {a.package}', '']
    nreg = 0
    for inst, (tname, base) in sorted(instances.items()):
        if used is not None and inst not in used:
            continue
        if tname not in types:
            left_out[inst] = (f'struct {tname} not understood at {where[tname]}' if tname in where else
                              f'no struct {tname} found in the headers')
            continue
        try:
            b = evaluate(base, defines)
        except ValueError:
            left_out[inst] = f'its address {base} is no integer constant, at {where[inst]}'
            continue
        out.append(f'internal object {inst} {{')
        out.append(f'    const val BASE: UInt = 0x{b:08X}u')
        for f, off, size, count in types[tname][0]:
            if f.startswith('RESERVED'):
                continue
            out.append(f'    const val {f}: UInt = 0x{b + off:08X}u' + (f'   // [{count}] x {size} B' if count > 1 else ''))
            nreg += 1
        out.append('}')
    out.append('')
    nbit = 0
    for name, val in sorted(defines.items()):
        if name in instances or name.startswith('__') or not re.fullmatch(r'[A-Z][A-Za-z0-9_]*', name):
            continue
        if used is not None and name not in used:
            continue
        if name.endswith(('_H', '_H_')) or 'VERSION' in name or name.startswith(('CMSIS', 'STM32')):
            continue
        try:
            v = evaluate(val, defines)
        except ValueError:
            left_out[name] = f'{val} is no integer constant, at {where[name]}'
            continue
        if name.endswith('_Pos'):
            out.append(f'internal const val {name}: Int = {v}')
        else:
            out.append(f'internal const val {name}: UInt = 0x{v:X}u')
        nbit += 1
    out.append('')
    for name, v in sorted(irqs.items(), key=lambda kv: kv[1]):
        if used is None or name in used:
            out.append(f'internal const val {name}: Int = {v}')
    # board pin map (`#define BTN_PORT GPIOA`, `#define BTN_PIN 0u`): NAME_PORT = the port's base address,
    # NAME_PIN = the pin number. The same names as in C; inside the package they win over cinterop's c.NAME_PIN.
    board = strip_comments(a.pins.read_text(encoding='utf-8', errors='replace')) if a.pins else ''
    out.append('')
    for name, port in re.findall(r'#define\s+(\w+)_PORT\s+(GPIO[A-Z])\b', board):
        if used is not None and f'{name}_PORT' not in used and f'{name}_PIN' not in used:
            continue
        pin = re.search(rf'#define\s+{name}_PIN\s+(.+)', board)
        try:
            base = evaluate(instances[port][1] if port in instances else '', defines)
        except ValueError:
            sys.exit(f'gen_regs: {a.pins}: {name}_PORT is {port}, which the headers do not define')
        try:
            number = evaluate(pin.group(1) if pin else '', defines)
        except ValueError:
            sys.exit(f'gen_regs: {a.pins}: {name}_PIN is not a pin number')
        out.append(f'internal const val {name}_PORT: UInt = 0x{base:08X}u   // {port}')
        out.append(f'internal const val {name}_PIN: Int = {number}')
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text('\n'.join(out) + '\n', encoding='utf-8', newline='\n')
    print(f'{a.out.name}: {sum(1 for i in instances if instances[i][0] in types)} peripherals, {nreg} registers, '
          f'{nbit} constants, {len(irqs)} IRQ numbers', flush=True)
    if used is not None:                                # with --all, nobody asked for the names that are left out
        for name, why in sorted(left_out.items()):
            print(f'gen_regs: warning: {name} left out: {why}', file=sys.stderr)


if __name__ == '__main__':
    main()
