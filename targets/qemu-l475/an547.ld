/* QEMU mps3-an547 (Cortex-M55 with an FPU, MVE and the Security Extension), with the start code and the layout of
 * l475.ld: the 256 KB of flash and 64 KB of RAM of the STM32L431 (1 MB and 96 KB with qbuild --large), a 4 KB stack
 * guard below the stack. Only the addresses differ. For the tests of the ARMv8.1-M cores.
 * The core starts in the Secure state and the program stays there, as on mps2-an505 (an505.ld): it is linked into
 * the Secure aliases of the machine's memories. The code is in the 2 MB RAM at 0x11000000 and the data in the
 * 512 KB DTCM at 0x30000000.
 * At reset this core reads the stack pointer and Reset_Handler at address 0, which is the ITCM: 512 KB, too small
 * for a --large program, with its Secure alias at 0x10000000. The ITCM holds only those two words, as the code
 * memory of mps2.ld does: start.c puts the null guard on the first 64 KB of the address space, which the MPU then
 * gives no access, and points VTOR at the vector table in the code memory. */
MEMORY
{
  BOOT  (r)   : ORIGIN = 0x10000000, LENGTH = 8
  FLASH (rx)  : ORIGIN = 0x11000000, LENGTH = DEFINED(kmicro_large) ? 1024K : 256K
  RAM   (rwx) : ORIGIN = 0x30000000, LENGTH = DEFINED(kmicro_large) ? 96K : 64K
}
ENTRY(Reset_Handler)
_estack = ORIGIN(RAM) + LENGTH(RAM);
SECTIONS
{
  .boot : { LONG(_estack) LONG(ABSOLUTE(Reset_Handler) | 1) } > BOOT
  .isr_vector : { KEEP(*(.isr_vector)) } > FLASH
  .text : { *(.text .text.*) *(.rodata .rodata.*) } > FLASH
  .ARM.extab : { *(.ARM.extab* .gnu.linkonce.armextab.*) } > FLASH
  .ARM.exidx : { __exidx_start = .; *(.ARM.exidx* .gnu.linkonce.armexidx.*) __exidx_end = .; } > FLASH
  .init_array : { __init_array_start = .; KEEP(*(SORT(.init_array.*))) KEEP(*(.init_array)) __init_array_end = .; }
    > FLASH
  _sidata = LOADADDR(.data);
  .data : { _sdata = .; *(.data .data.*) . = ALIGN(4); _edata = .; } > RAM AT > FLASH
  .bss (NOLOAD) : { _sbss = .; *(.bss .bss.* COMMON) . = ALIGN(4); _ebss = .; } > RAM
  .stack_guard (NOLOAD) : { . += 256; . = ALIGN(4096); _sguard = .; . += 4096; _eguard = .; } > RAM
  _end = .; end = .;
}
