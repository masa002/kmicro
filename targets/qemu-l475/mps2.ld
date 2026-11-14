/* QEMU mps2-an385 (Cortex-M3) and mps2-an500 (Cortex-M7 with a double-precision FPU), with the start code and the
 * layout of l475.ld: 1 MB of code and 96 KB of RAM, a 4 KB stack guard below the stack. Only the addresses differ:
 * these machines have their code memory at 0 and RAM at 0x20000000. For the tests of the cores that the STM32L475's
 * Cortex-M4F does not run (the Cortex-M7), and for a Cortex-M3 that refuses FPU and DSP instructions.
 * The first 64 KB hold only the two words the core reads at reset (stack pointer, Reset_Handler): start.c makes that
 * range a no-access MPU region, the null guard, and points VTOR at the real vector table, which follows it. */
MEMORY
{
  FLASH (rx)  : ORIGIN = 0x00000000, LENGTH = 1024K
  RAM   (rwx) : ORIGIN = 0x20000000, LENGTH = 96K
}
ENTRY(Reset_Handler)
_estack = ORIGIN(RAM) + LENGTH(RAM);
SECTIONS
{
  .boot : { LONG(_estack) LONG(ABSOLUTE(Reset_Handler) | 1) } > FLASH
  .isr_vector 0x10000 : { KEEP(*(.isr_vector)) } > FLASH
  .text : { *(.text .text.*) *(.rodata .rodata.*) } > FLASH
  .ARM.extab : { *(.ARM.extab* .gnu.linkonce.armextab.*) } > FLASH
  .ARM.exidx : { __exidx_start = .; *(.ARM.exidx* .gnu.linkonce.armexidx.*) __exidx_end = .; } > FLASH
  .init_array : { __init_array_start = .; KEEP(*(SORT(.init_array.*))) KEEP(*(.init_array)) __init_array_end = .; } > FLASH
  _sidata = LOADADDR(.data);
  .data : { _sdata = .; *(.data .data.*) . = ALIGN(4); _edata = .; } > RAM AT > FLASH
  .bss (NOLOAD) : { _sbss = .; *(.bss .bss.* COMMON) . = ALIGN(4); _ebss = .; } > RAM
  .stack_guard (NOLOAD) : { . += 256; . = ALIGN(4096); _sguard = .; . += 4096; _eguard = .; } > RAM
  _end = .; end = .;
}
