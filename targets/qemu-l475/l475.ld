/* QEMU b-l475e-iot01a (STM32L475VG: 1 MB flash at 0x08000000, SRAM1 96 KB at 0x20000000).
 * The emulated chip is larger than the STM32L431 kmicro aims at. This script gives a program the memory of the
 * smaller chip, 256 KB of flash and 64 KB of RAM: one that does not fit fails to link, and one that needs more stack
 * than the 64 KB leave runs into the guard. qbuild --large defines kmicro_large, which gives the program the whole
 * STM32L475: for a test that tests/run_all.py or tools/difftest.py marks large.
 * RAM: .data, .bss (the Kotlin heap and the runtime's globals), a 4 KB guard, then the stack up to the top. The
 * guard is an MPU no-access region (start.c): an overflowing stack faults there before it writes .bss. It is larger
 * than the largest frames of the runtime's C code (1024 bytes) and of the standard library (2984 bytes, in Regex;
 * tools/frames.py), so no call can step over it; run_all checks that for every test image. The 256 bytes below it are left unused: the stack_guard test watches them. */
MEMORY
{
  FLASH (rx)  : ORIGIN = 0x08000000, LENGTH = DEFINED(kmicro_large) ? 1024K : 256K
  RAM   (rwx) : ORIGIN = 0x20000000, LENGTH = DEFINED(kmicro_large) ? 96K : 64K
}
ENTRY(Reset_Handler)
_estack = ORIGIN(RAM) + LENGTH(RAM);
SECTIONS
{
  .isr_vector : { KEEP(*(.isr_vector)) } > FLASH
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
