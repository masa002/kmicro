/* QEMU mps2-an505 (Cortex-M33 with an FPU and the Security Extension), with the start code and the layout of
 * l475.ld: the 256 KB of flash and 64 KB of RAM of the STM32L431 (1 MB and 96 KB with qbuild --large), a 4 KB stack
 * guard below the stack. Only the addresses differ. For the tests of the ARMv8-M cores.
 * The core starts in the Secure state and the program stays there, as a program that does not use the Security
 * Extension does: it never enables the SAU, so every address is Secure. It is linked into the Secure aliases of the
 * machine's memories: the 4 MB code memory at 0x10000000, where the core reads the Secure vector table at reset, and
 * the 2 MB RAM at 0x38000000 (the RAM at 0x30000000 has 32 KB only). Address 0 is the other alias of the code
 * memory, as it is an alias of flash on the STM32L475: start.c puts the null guard on the first 64 KB, which the
 * MPU then gives no access. */
MEMORY
{
  FLASH (rx)  : ORIGIN = 0x10000000, LENGTH = DEFINED(kmicro_large) ? 1024K : 256K
  RAM   (rwx) : ORIGIN = 0x38000000, LENGTH = DEFINED(kmicro_large) ? 96K : 64K
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
