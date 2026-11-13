/* QEMU b-l475e-iot01a (STM32L475VG: 1 MB flash at 0x08000000, SRAM1 96 KB at 0x20000000).
 * The emulated chip is larger than the STM32L431 kmicro aims at (256 KB flash, 64 KB RAM), and nothing checks a
 * program against the smaller chip here: compare the size line qbuild prints.
 * RAM: .data, .bss (the Kotlin heap and the runtime's globals), a 256-byte guard, then the stack up to the top. The
 * guard is an MPU no-access region (start.c): an overflowing stack faults there before it writes .bss. */
MEMORY
{
  FLASH (rx)  : ORIGIN = 0x08000000, LENGTH = 1024K
  RAM   (rwx) : ORIGIN = 0x20000000, LENGTH = 96K
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
  .stack_guard (NOLOAD) : { . = ALIGN(256); _sguard = .; . += 256; _eguard = .; } > RAM
  _end = .; end = .;
}
