# Copyright 2026 the kmicro authors (NOTICE).
# SPDX-License-Identifier: Apache-2.0
"""tools/isr_check.py on canned objdump output: which handlers it finds and what it reports.

usage: python tests/unit/test_isr_check.py      (or python -m unittest discover tests/unit)
"""
import io
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'tools'))
import isr_check  # noqa: E402


def disassembly(functions):
    """objdump -d --no-show-raw-insn text: functions = [(address, name, [called function names])]."""
    addr = {name: a for a, name, _ in functions}
    out = ['image.elf:     file format elf32-littlearm', '', '', 'Disassembly of section .text:']
    for a, name, called in functions:
        out += ['', f'{a:08x} <{name}>:', f' {a:7x}:\tpush\t{{r7, lr}}']
        out += [f' {a + 2 + 4 * i:7x}:\tbl\t{addr[c]:x} <{c}>' for i, c in enumerate(called)]
        out.append(f' {a + 2 + 4 * len(called):7x}:\tpop\t{{r7, pc}}')
    return '\n'.join(out) + '\n'


def vector_table(words, base=0x08000000):
    """objdump -s -j .isr_vector text for these 32-bit words."""
    out = ['image.elf:     file format elf32-littlearm', '', 'Contents of section .isr_vector:']
    for i in range(0, len(words), 4):
        groups = [w.to_bytes(4, 'little').hex() for w in words[i:i + 4]]
        out.append(f' {base + 4 * i:x} ' + ' '.join(groups).ljust(35) + '  ' + '.' * (4 * len(groups)))
    return '\n'.join(out) + '\n'


FUNCS = [
    (0x08000100, 'Reset_Handler', ['main']),
    (0x08000140, 'main', ['kfun:app#loop(){}', 'kfun:kotlin#<Int-box>(kotlin.Int){}kotlin.Any']),
    (0x08000180, 'fault', []),
    (0x080001c0, 'kfun:app#loop(){}', ['AllocInstance']),
    (0x08000200, 'kfun:irq#onTick(){}', ['kfun:irq#count(){}']),        # the vector table's only name for it
    (0x08000240, 'kfun:irq#count(){}', []),
    (0x08000280, 'kfun:irq#record(){}', ['kfun:irq#count(){}', 'alloc_block']),
    (0x080002c0, 'kfun:irq#check(){}', ['ThrowIndexOutOfBounds']),
    (0x08000300, 'ThrowIndexOutOfBounds', ['AllocInstance']),
    (0x08000340, 'AllocInstance', ['alloc_block']),
    (0x08000380, 'alloc_block', []),
    (0x080003c0, 'kfun:kotlin#<Int-box>(kotlin.Int){}kotlin.Any', ['AllocInstance']),
]


def table(systick):
    """A Cortex-M vector table: stack, reset, faults, SysTick (vector 15) = systick (a Thumb address)."""
    words = [0x20018000, 0x08000101] + [0x08000181] * 13 + [systick | 1]
    words[7:11] = [0, 0, 0, 0]
    return words


class IsrCheck(unittest.TestCase):
    def run_check(self, systick, funcs=FUNCS, **kw):
        return isr_check.analyse(disassembly(funcs), vector_table(table(systick)), **kw)

    def test_vector_table_words(self):
        self.assertEqual(isr_check.vector_words(vector_table(table(0x08000200))), (table(0x08000201), None))

    def test_clean_handler_passes(self):
        lines, bad, n = self.run_check(0x08000200)
        self.assertEqual((bad, n), (0, 2), lines)                     # fault and onTick, not Reset_Handler
        self.assertIn('2 interrupt handler(s) checked: no path to an allocation', lines)

    def test_allocating_handler_found_through_the_vector_table(self):
        # kfun:irq#record(){} has no handler-like name: only the vector table shows that it is one
        lines, bad, _ = self.run_check(0x08000280)
        self.assertEqual(bad, 1, lines)
        self.assertIn('ALLOC  kfun:irq#record(){}: kfun:irq#record(){} -> alloc_block', lines)

    def test_handler_named_like_a_handler_is_checked(self):
        funcs = FUNCS + [(0x08000400, 'kfun:irq#SysTickHandler(){}', ['kfun:irq#record(){}'])]
        lines, bad, n = self.run_check(0x08000200, funcs)
        self.assertEqual((bad, n), (1, 3), lines)
        self.assertTrue(any(l.startswith('ALLOC  kfun:irq#SysTickHandler(){}') for l in lines), lines)

    def test_callback(self):
        lines, bad, _ = self.run_check(0x08000200, callbacks=['kfun:irq#record(){}'])
        self.assertEqual(bad, 1, lines)
        with self.assertRaises(ValueError):
            self.run_check(0x08000200, callbacks=['kfun:irq#nope(){}'])

    def test_throw_paths_are_not_followed(self):
        lines, bad, _ = self.run_check(0x080002c0)
        self.assertEqual(bad, 0, lines)
        helper = 'kfun:kotlin.native.internal#ThrowNoWhenBranchMatchedException(){}kotlin.Nothing'
        funcs = FUNCS + [(0x08000400, 'kfun:irq#pick(){}', [helper]), (0x08000440, helper, ['AllocInstance'])]
        lines, bad, _ = self.run_check(0x08000400, funcs)
        self.assertEqual(bad, 0, lines)

    def test_a_user_function_named_like_a_throw_helper_is_followed(self):
        for name in ('kfun:irq#sendOrThrow(kotlin.Int){}kotlin.Int', 'kfun:irq#ThrowAway(){}',
                     'kfun:kotlin#getOrThrow(){}'):
            funcs = FUNCS + [(0x08000400, 'kfun:irq#tick(){}', [name]), (0x08000440, name, ['AllocInstance'])]
            lines, bad, _ = self.run_check(0x08000400, funcs)
            self.assertEqual(bad, 1, (name, lines))
            self.assertIn(f'ALLOC  kfun:irq#tick(){{}}: kfun:irq#tick(){{}} -> {name} -> AllocInstance', lines)

    def test_boxing_in_thread_code_only_with_the_flag(self):
        lines, bad, _ = self.run_check(0x08000200)
        self.assertEqual(bad, 0, lines)
        lines, bad, _ = self.run_check(0x08000200, boxing=True)
        self.assertEqual(bad, 1, lines)
        self.assertIn('BOX    main -> kfun:kotlin#<Int-box>(kotlin.Int){}kotlin.Any', lines)

    def test_boxing_in_a_handler(self):
        funcs = FUNCS + [(0x08000400, 'kfun:irq#boxes(){}', ['kfun:kotlin#<Int-box>(kotlin.Int){}kotlin.Any'])]
        lines, bad, _ = self.run_check(0x08000400, funcs)
        self.assertEqual(bad, 1, lines)
        self.assertIn('BOX    kfun:irq#boxes(){}: kfun:irq#boxes(){} -> kfun:kotlin#<Int-box>(kotlin.Int){}kotlin.Any',
                      lines)

    def test_indirect_calls_are_counted(self):
        # a call through a pointer, also as a tail call (bx r0) or a load into pc; none of them is a return
        for insn in ('blx\tr3', 'blx\tip', 'bx\tr0', 'bxne\tr3', 'mov\tpc, r2', 'ldr.w\tpc, [r4, #8]'):
            text = disassembly(FUNCS).replace('<fault>:\n', f'<fault>:\n 8000180:\t{insn}\n')
            lines, bad, _ = isr_check.analyse(text, vector_table(table(0x08000200)))
            self.assertEqual(bad, 0, lines)
            self.assertIn('note   fault: 1 indirect call site(s) not followed: not proven clean', lines, insn)

    def test_returns_are_no_indirect_calls(self):
        returns = ('bx\tlr', 'bxeq\tlr', 'mov\tpc, lr', 'ldr.w\tpc, [sp], #4', 'ldmia.w\tsp!, {r4, r5, pc}')
        text = disassembly(FUNCS).replace('<fault>:\n', '<fault>:\n' + ''.join(f' 8000180:\t{i}\n' for i in returns))
        lines, _, _ = isr_check.analyse(text, vector_table(table(0x08000200)))
        self.assertEqual(lines, ['2 interrupt handler(s) checked: no path to an allocation'])

    def test_an_image_without_the_table_says_so(self):
        # kfun:irq#record(){} allocates and is a handler only by the table: without the table nobody looks at it
        lines, bad, n = isr_check.analyse(disassembly(FUNCS + [(0x08000400, 'HardFault_Handler', [])]), '')
        self.assertEqual((bad, n), (0, 1), lines)
        self.assertEqual(lines[-1], '1 interrupt handler(s) checked: no path to an allocation')
        self.assertEqual(lines[0], 'note   no vector table: the image has no section .isr_vector. Only the functions '
                         'named like handlers were checked; --vectors SECTION names the section that holds the table')
        lines, bad, _ = self.run_check(0x08000280)                     # the same image with its table
        self.assertEqual(bad, 1, lines)
        self.assertFalse(any('no vector table' in l for l in lines), lines)

    def test_the_table_in_a_section_of_another_name(self):
        def objdump(elf, *args):
            if args == ('-h',):
                return 'Idx Name          Size\n  0 .vectors      00000040\n  1 .text         00000400\n'
            if args == ('-s', '-j', '.vectors'):
                return vector_table(table(0x08000280)).replace('.isr_vector', '.vectors')
            return disassembly(FUNCS + [(0x08000400, 'HardFault_Handler', [])]) if args[0] == '-d' else self.fail(args)

        def run(*argv):
            out = io.StringIO()
            with mock.patch.object(sys, 'argv', ['isr_check.py', __file__, *argv]), \
                    mock.patch.object(isr_check, 'objdump', objdump), mock.patch.object(sys, 'stdout', out), \
                    mock.patch.object(sys, 'stderr', out), self.assertRaises(SystemExit) as e:
                isr_check.main()
            return e.exception.code, out.getvalue()

        code, out = run('--vectors', '.vectors')
        self.assertEqual(code, 1, out)
        self.assertIn('ALLOC  kfun:irq#record(){}: kfun:irq#record(){} -> alloc_block', out)
        code, out = run()                                              # the default name: not in this image
        self.assertEqual(code, 0, out)
        self.assertIn('note   no vector table: the image has no section .isr_vector.', out)
        code, out = run('--vectors', '.intvec')
        self.assertEqual(code, 2, out)
        self.assertIn('no section .intvec (--vectors)', out)

    def test_every_entry_of_a_handler_table_is_a_handler(self):
        # no vector table: a plain table has no stack pointer and no reset handler to leave out, so its first two
        # entries are handlers too. kfun:irq#record(){} allocates and has no handler-like name
        handlers = vector_table([0x08000280, 0x08000201, 0, 0x08000181]).replace('.isr_vector', '.irq_handlers')
        lines, bad, n = isr_check.analyse(disassembly(FUNCS), '', handlers=handlers)
        self.assertEqual((bad, n), (1, 3), lines)
        self.assertIn('ALLOC  kfun:irq#record(){}: kfun:irq#record(){} -> alloc_block', lines)
        self.assertFalse(any('no vector table' in l for l in lines), lines)
        lines, _, _ = isr_check.analyse(disassembly(FUNCS), '', handlers=handlers.replace('81010008', '85010008'))
        self.assertIn('note   handler table entry 3 (0x08000185) is not the start of a function', lines)

    def test_the_handler_table_is_found_by_its_section(self):
        def objdump(elf, *args):
            if args == ('-h',):
                return 'Idx Name          Size\n  0 .vectors      00000020\n  1 .irq_table    00000010\n'
            if args == ('-s', '-j', '.irq_table'):
                return vector_table([0x08000280, 0x08000201]).replace('.isr_vector', '.irq_table')
            return disassembly(FUNCS) if args[0] == '-d' else self.fail(args)

        def run(*argv):
            out = io.StringIO()
            with mock.patch.object(sys, 'argv', ['isr_check.py', __file__, *argv]), \
                    mock.patch.object(isr_check, 'objdump', objdump), mock.patch.object(sys, 'stdout', out), \
                    mock.patch.object(sys, 'stderr', out), self.assertRaises(SystemExit) as e:
                isr_check.main()
            return e.exception.code, out.getvalue()

        code, out = run('--handlers', '.irq_table')
        self.assertEqual(code, 1, out)
        self.assertIn('ALLOC  kfun:irq#record(){}: kfun:irq#record(){} -> alloc_block', out)
        code, out = run()                                              # the default name: not in this image
        self.assertEqual(code, 2, out)
        self.assertIn('no interrupt handler found', out)
        code, out = run('--handlers', '.nope')
        self.assertEqual(code, 2, out)
        self.assertIn('no section .nope (--handlers)', out)

    def test_the_table_at_the_start_of_the_code_section(self):
        # `.text : { KEEP(*(.isr_vector)) *(.text*) }`: after the 16 vectors the section goes on with Reset_Handler's
        # code. One of its words is a literal pool entry, the address of the allocating thread function
        # kfun:app#loop(){}: no vector.
        code = [0xbd80b580, 0xf000b580, 0x080001c1, 0x46c04770]
        text = vector_table(table(0x08000200) + code, base=0x080000c0).replace('.isr_vector', '.text')
        lines, bad, n = isr_check.analyse(disassembly(FUNCS), text, section='.text')
        self.assertEqual((bad, n), (0, 2), lines)
        self.assertEqual(lines, ['note   the section .text goes on with code: its first 16 words, up to the function '
                                 'Reset_Handler, were read as the vector table',
                                 '2 interrupt handler(s) checked: no path to an allocation'])
        text = vector_table(table(0x08000280) + code, base=0x080000c0).replace('.isr_vector', '.text')
        lines, bad, _ = isr_check.analyse(disassembly(FUNCS), text, section='.text')
        self.assertEqual(bad, 1, lines)                                # a handler of the table is still found
        self.assertIn('ALLOC  kfun:irq#record(){}: kfun:irq#record(){} -> alloc_block', lines)

    def test_nothing_to_check_is_an_error(self):
        with self.assertRaises(ValueError):
            isr_check.analyse('', '')
        with self.assertRaises(ValueError):                            # functions, but no handler
            isr_check.analyse(disassembly([(0x08000100, 'main', [])]), '')

    def test_missing_elf_exits_2(self):
        with mock.patch.object(sys, 'argv', ['isr_check.py', 'no_such.elf']), \
                mock.patch.object(sys, 'stderr'), self.assertRaises(SystemExit) as e:
            isr_check.main()
        self.assertEqual(e.exception.code, 2)


if __name__ == '__main__':
    unittest.main()
