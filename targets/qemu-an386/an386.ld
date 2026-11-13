/* QEMU mps2-an386 (Cortex-M4 + FPU): 4 MB SSRAM1 for code at 0, 4 MB SSRAM2/3 at 0x20000000 (the stack), 16 MB
 * PSRAM at 0x21000000 (data, bss, heap, stack). For unit tests that need more memory than the device has: a
 * firmware's C tests run against its Kotlin modules, compiled exactly as for the device, next to mocks of megabytes
 * (an external flash chip, for example). Start code: start.c; link librdimon.a (semihosting stdio) and --wrap=_exit. */
MEMORY
{
  CODE  (rx)  : ORIGIN = 0x00000000, LENGTH = 4M
  SSRAM (rwx) : ORIGIN = 0x20000000, LENGTH = 4M
  RAM   (rwx) : ORIGIN = 0x21000000, LENGTH = 16M
}
ENTRY(Reset_Handler)
_estack = ORIGIN(RAM) + LENGTH(RAM);   /* top of PSRAM: newlib sbrk grows the heap up toward it */
SECTIONS
{
  .isr_vector : { KEEP(*(.isr_vector)) } > CODE
  .text : { *(.text .text.*) *(.rodata .rodata.*) KEEP(*(.init)) KEEP(*(.fini)) } > CODE
  .ARM.extab : { *(.ARM.extab* .gnu.linkonce.armextab.*) } > CODE
  .ARM.exidx : { __exidx_start = .; *(.ARM.exidx* .gnu.linkonce.armexidx.*) __exidx_end = .; } > CODE
  .preinit_array : { __preinit_array_start = .; KEEP(*(.preinit_array*)) __preinit_array_end = .; } > CODE
  .init_array : { __init_array_start = .; KEEP(*(SORT(.init_array.*))) KEEP(*(.init_array)) __init_array_end = .; } > CODE
  .fini_array : { __fini_array_start = .; KEEP(*(.fini_array*)) __fini_array_end = .; } > CODE
  _sidata = LOADADDR(.data);
  .data : { _sdata = .; *(.data .data.*) . = ALIGN(4); _edata = .; } > RAM AT > CODE
  .bss (NOLOAD) : { _sbss = .; *(.bss .bss.* COMMON) . = ALIGN(4); _ebss = .; } > RAM
  . = ALIGN(8);
  _end = .; end = .;
}
