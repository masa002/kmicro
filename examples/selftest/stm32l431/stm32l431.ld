/* STM32L431xC: 256 KB flash at 0x08000000, 64 KB SRAM at 0x20000000 (SRAM1 48 KB, then SRAM2 16 KB at 0x2000C000).
 * RAM: .data, .bss (the Kotlin heap and the runtime's globals), then the stack, which grows down from the top. */
MEMORY
{
  FLASH (rx)  : ORIGIN = 0x08000000, LENGTH = 256K
  RAM   (rwx) : ORIGIN = 0x20000000, LENGTH = 64K
}
ENTRY(Reset_Handler)
_estack = ORIGIN(RAM) + LENGTH(RAM);
_min_stack = 8K;
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
  _end = .; end = .;
  ASSERT(_ebss + _min_stack <= _estack, "less than 8 KB of RAM is left for the stack")
}
