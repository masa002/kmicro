#!/usr/bin/env python3
"""Generate Kotlin register constants from CMSIS headers: every register address and every bit constant.

    python tools/gen_regs.py --header core_cm4.h --header stm32l431xx.h [--pins board.h] --sources kotlin/
                             --out kotlin/Regs.kt --package NAME [--all]

Nothing is typed by hand: addresses come from the CMSIS struct layouts (offsets computed here) and the instance
macros (`#define RCC ((RCC_TypeDef *) RCC_BASE)`); bit constants from the `#define X_Pos / X_Msk / X` macros.
Registers are `object RCC { const val CR: UInt = 0x40021000u ... }`: reading RCC.CR is a compile-time constant
(the object is never created). Kotlin reads and writes them through hw_rd32 / hw_wr32 (support/hw.h). With
--sources only the names the Kotlin files in that folder and its subfolders use are emitted (the full set is 13,000
lines and slow to compile), and a warning names each of them that the headers define but that is left out, with the
reason: a struct with a union or a bit field, a macro that is no integer constant. examples/irq shows the whole flow.
"""
import re
import sys
from pathlib import Path

SIZES = {'uint32_t': 4, 'uint16_t': 2, 'uint8_t': 1, 'int32_t': 4, 'int16_t': 2, 'int8_t': 1}


def strip_comments(s):
    """s without its comments. A comment's line ends stay, so that line numbers do."""
    return re.sub(r'/\*.*?\*/|//[^\n]*', lambda m: '\n' * m.group(0).count('\n'), s, flags=re.S)


def layout(body, defines, types):
    """The body of a struct -> ([(field, offset, size, count)], the struct's size). Raises ValueError for what is no
    plain register layout: a union, a bit field, a pointer, an unknown type, an array size that is no constant."""
    fields, off = [], 0
    for decl in body.split(';'):
        decl = re.sub(r'\b(__IO|__I|__O|__IM|__OM|__IOM|volatile|const)\b', ' ', decl).strip()
        if not decl:
            continue
        d = re.match(r'(\w+)\s+(.+)$', decl, re.S)
        size = d and (SIZES.get(d.group(1)) or (types[d.group(1)][1] if d.group(1) in types else None))
        if not size:
            raise ValueError(decl)
        align = min(size, 4)
        for item in d.group(2).split(','):              # `uint32_t CR1, CR2;` declares two registers
            f = re.fullmatch(r'\s*(\w+)\s*(?:\[([^\]]+)\])?\s*', item)
            if not f:
                raise ValueError(decl)
            off = (off + align - 1) // align * align
            count = evaluate(f.group(2), defines) if f.group(2) else 1
            fields.append((f.group(1), off, size, count))
            off += size * count
    return fields, (off + 3) // 4 * 4


def parse(text, header, defines, types, instances, irqs, where):
    """Adds what the header defines to the tables. where: a macro or a struct -> 'header line N', and for a struct
    that is not understood also the declaration that is the reason."""
    for n, line in enumerate(text.splitlines(), 1):     # the macros first: a struct may size an array with one
        d = re.match(r'\s*#define\s+(\w+)\s+(.+?)\s*$', line)
        if not d:
            continue
        name, val = d.group(1), d.group(2)
        where[name] = f'{header} line {n}'
        inst = re.match(r'\(\(\s*(\w+)\s*\*\s*\)\s*(\w+)\s*\)$', val)
        if inst:
            instances[name] = (inst.group(1), inst.group(2))
        elif '(' not in name:
            defines[name] = val
    for m in re.finditer(r'^\s*(\w+_IRQn)\s*=\s*(-?\d+)', text, re.M):
        irqs[m.group(1)] = int(m.group(2))
    # A body may hold a union or a struct in braces. It is not understood then, but reported under its own name.
    for m in re.finditer(r'typedef\s+struct\s*\w*\s*\{((?:[^{}]|\{[^{}]*\})*)\}\s*(\w+)\s*;', text):
        n = text.count('\n', 0, m.start()) + 1
        where[m.group(2)] = f'{header} line {n}'
        try:
            types[m.group(2)] = layout(m.group(1), defines, types)
        except ValueError as e:                         # its instances are left out
            where[m.group(2)] += ': ' + ' '.join(str(e).split())


def evaluate(expr, defines, depth=0):
    """The value of a C integer constant expression, in 32 bits. Raises ValueError for anything else: an unknown
    name, a floating-point number, an operator other than + - * / % << >> | & ^ ~."""
    if depth > 40:
        raise ValueError(expr)
    e = re.sub(r'\b(0x[0-9A-Fa-f]+|\d+)[uUlL]+\b', r'\1', expr)
    e = re.sub(r'\(\s*(uint32_t|int32_t|uint16_t|uint8_t)\s*\)', '', e)

    def sub(m):
        n = m.group(0)
        if n in defines:
            return '(' + str(evaluate(defines[n], defines, depth + 1)) + ')'
        raise ValueError(n)
    e = re.sub(r'\b[A-Za-z_]\w*\b', sub, e)
    e = re.sub(r'\b0+(?=[0-7]+\b)', '0o', e)            # C's octal: 017
    if not re.fullmatch(r'[\s0-9xXoA-Fa-f()+\-*/%<>|&~^]+', e):
        raise ValueError(expr)
    try:
        v = eval(e.replace('/', '//'))                  # // and %: as in C while no operand is negative
    except (SyntaxError, ArithmeticError, TypeError):
        raise ValueError(expr) from None
    if type(v) is not int:                              # 8e6 is a floating-point number
        raise ValueError(expr)
    return v & 0xFFFFFFFF


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
    defines, types, instances, irqs, where = {}, {}, {}, {}, {}
    for h in a.header:
        parse(strip_comments(h.read_text(encoding='utf-8', errors='replace')), h.name, defines, types, instances, irqs,
              where)
    left_out = {}                                       # a name that is wanted -> why it is not in the file
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
