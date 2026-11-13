"""toolchain/kn.py: the Kotlin name of a C name (camel) and the --c-api aliases built from it.

python -m unittest discover -s tests/unit
"""
import contextlib
import io
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'toolchain'))
import kn  # noqa: E402

NAMES = [
    ('crc32_update', 'crc32Update'),
    ('gc_chains', 'gcChains'),
    ('hello', 'hello'),
    ('fooBar', 'fooBar'),
    ('USART1_IRQHandler', 'usart1IrqHandler'),
    ('DMA1_Channel3_IRQHandler', 'dma1Channel3IrqHandler'),
    ('RTC_Alarm_IRQHandler', 'rtcAlarmIrqHandler'),
    ('SysTick_Handler', 'sysTickHandler'),
    ('HardFault_Handler', 'hardFaultHandler'),
    ('PendSV_Handler', 'pendSVHandler'),
    ('TIM1_UP_TIM16_IRQHandler', 'tim1UpTim16IrqHandler'),
    ('RCC_CRS_IRQHandler', 'rccCrsIrqHandler'),
    ('EXTI15_10_IRQHandler', 'exti15_10IrqHandler'),
    ('USB_send', 'usbSend'),
    ('adc_read_mV', 'adcReadMV'),
]

IR = '''
define i32 @"kfun:app#crc32Update(kotlin.Int){}kotlin.Int"(i32 %0) {
  ret i32 %0
}
define void @"kfun:app#SysTickHandler(){}"() {
  ret void
}
define void @"kfun:app#tim1UpTim16IrqHandler(){}"() {
  ret void
}
'''


class Camel(unittest.TestCase):
    def test_table(self):
        for c, k in NAMES:
            self.assertEqual(kn.camel(c), k, c)

    def test_legacy_spelling(self):
        self.assertEqual(kn.kotlin_names('SysTick_Handler'), ['sysTickHandler', 'SysTickHandler'])
        self.assertEqual(kn.kotlin_names('crc32_update'), ['crc32Update'])


class Aliases(unittest.TestCase):
    def aliases(self, names):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            lines, missing = kn.add_c_aliases(IR, names, 'app')
        return lines, missing, err.getvalue()

    def test_new_and_old_spelling(self):
        lines, missing, err = self.aliases(['crc32_update', 'TIM1_UP_TIM16_IRQHandler', 'SysTick_Handler'])
        self.assertEqual(missing, [])
        self.assertIn('@crc32_update = alias i32 (i32), ptr @"kfun:app#crc32Update(kotlin.Int){}kotlin.Int"', lines)
        self.assertIn('@SysTick_Handler = alias void (), ptr @"kfun:app#SysTickHandler(){}"', lines)
        self.assertIn('rename it sysTickHandler', err)

    def test_missing(self):
        self.assertEqual(self.aliases(['crc16_update'])[1], ['crc16_update'])

    def test_collision_is_an_error(self):
        for pair in (['crc32_update', 'crc_32_update'], ['foo_bar', 'fooBar']):
            with self.assertRaises(SystemExit) as e:
                self.aliases(pair)
            self.assertIn('both become the Kotlin name', str(e.exception))


if __name__ == '__main__':
    unittest.main()
