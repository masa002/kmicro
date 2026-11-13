"""tools/isr_check.py on canned objdump output: which handlers it finds and what it reports.

usage: python tests/unit/test_isr_check.py      (or python -m unittest discover tests/unit)
"""
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
        self.assertEqual(isr_check.vector_words(vector_table(table(0x08000200))), table(0x08000201))

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
