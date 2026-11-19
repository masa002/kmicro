/* QEMU raspi0, a Raspberry Pi Zero: 512 MB of RAM from address 0, into which QEMU loads the image (-kernel). The
 * image lies in the second megabyte, not at 0x8000, where the firmware of the board puts one: the first megabyte
 * is the null guard, which the MMU does not map (start.c).
 * The script gives a program the memory of the STM32L431 kmicro aims at, as targets/qemu-l475/l475.ld does and for
 * the same reason: 256 KB for the code and the constants (FLASH) and 64 KB of RAM. One that does not fit fails to
 * link, and one that needs more stack than the 64 KB leave runs into the guard. qbuild --large defines kmicro_large,
 * which gives 1 MB and 96 KB.
 * RAM: .data, .bss (the Kotlin heap and the runtime's globals), a 4 KB guard, then the stack up to the top. The
 * guard is a page the MMU does not map: an overflowing stack faults there before it writes .bss. The 256 bytes
 * below it are left unused: the stack_guard test watches them.
 * In the same megabyte, above the program's memory and not counted as its RAM: the translation tables of the MMU,
 * and the stacks of the exception modes, each above an unmapped page. */
MEMORY
{
  FLASH (rx)  : ORIGIN = 0x00100000, LENGTH = DEFINED(kmicro_large) ? 1024K : 256K
  RAM   (rwx) : ORIGIN = 0x00200000, LENGTH = DEFINED(kmicro_large) ? 96K : 64K
}
ENTRY(vectors)
_sram = ORIGIN(RAM);
_estack = ORIGIN(RAM) + LENGTH(RAM);
_ttb = ORIGIN(RAM) + 0x40000;           /* the first-level table: 4096 entries, 16 KB */
_ttb2 = _ttb + 0x4000;                  /* the second-level table of this megabyte: 256 entries, 1 KB */
_irq_guard = ORIGIN(RAM) + 0x50000;     /* 4 KB, then the stack of IRQ mode: 16 KB */
_irq_stack = _irq_guard + 0x5000;
_exc_guard = _irq_stack;                /* 4 KB, then the stack FIQ, Abort and Undefined mode share: 4 KB */
_exc_stack = _exc_guard + 0x2000;
SECTIONS
{
  .vectors : { KEEP(*(.vectors)) } > FLASH
  .irq_handlers : { KEEP(*(.irq_handlers)) } > FLASH
  .text : { _sirq_entry = .; *(.irq_entry) _eirq_entry = .; *(.text .text.*) *(.rodata .rodata.*) } > FLASH
  .ARM.extab : { *(.ARM.extab* .gnu.linkonce.armextab.*) } > FLASH
  .ARM.exidx : { __exidx_start = .; *(.ARM.exidx* .gnu.linkonce.armexidx.*) __exidx_end = .; } > FLASH
  .init_array : { __init_array_start = .; KEEP(*(SORT(.init_array.*))) KEEP(*(.init_array))
                __init_array_end = .; } > FLASH
  _sidata = LOADADDR(.data);
  .data : { _sdata = .; *(.data .data.*) . = ALIGN(4); _edata = .; } > RAM AT > FLASH
  .bss (NOLOAD) : { _sbss = .; *(.bss .bss.* COMMON) . = ALIGN(4); _ebss = .; } > RAM
  .stack_guard (NOLOAD) : { . += 256; . = ALIGN(4096); _sguard = .; . += 4096; _eguard = .; } > RAM
  _end = .; end = .;
}
