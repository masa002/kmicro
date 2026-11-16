/* QEMU mps3-an536, a Cortex-R52: RAM from 0x20000000 (the machine's DDR), into which QEMU loads the image
 * (-kernel). The machine also has 512 KB of RAM at address 0, which the program does not use: start.c leaves it
 * out of the MPU's regions, so a null pointer faults.
 * The script gives a program the memory of the STM32L431 kmicro aims at, as targets/qemu-l475/l475.ld does and for
 * the same reason: 256 KB for the code and the constants (FLASH) and 64 KB of RAM. One that does not fit fails to
 * link, and one that needs more stack than the 64 KB leave runs into the guard. qbuild --large defines kmicro_large,
 * which gives 1 MB and 96 KB.
 * RAM: .data, .bss (the Kotlin heap and the runtime's globals), a 4 KB guard, then the stack up to the top. The
 * guard belongs to no region of the MPU (start.c): an overflowing stack faults there before it writes .bss. The
 * 256 bytes below it are left unused: the stack_guard test watches them.
 * Above the program's memory and not counted as its RAM: the stacks of the exception modes, each above 4 KB that
 * belong to no region either. */
MEMORY
{
  FLASH (rx)  : ORIGIN = 0x20000000, LENGTH = DEFINED(kmicro_large) ? 1024K : 256K
  RAM   (rwx) : ORIGIN = 0x20100000, LENGTH = DEFINED(kmicro_large) ? 96K : 64K
}
ENTRY(vectors)
_sflash = ORIGIN(FLASH);
_eflash = ORIGIN(FLASH) + LENGTH(FLASH);
_sram = ORIGIN(RAM);
_estack = ORIGIN(RAM) + LENGTH(RAM);
_irq_guard = ORIGIN(RAM) + 0x50000;     /* 4 KB, then the stack of IRQ mode: 16 KB */
_irq_stack = _irq_guard + 0x5000;
_exc_guard = _irq_stack;                /* 4 KB, then the stack FIQ, Abort and Undefined mode share: 4 KB */
_exc_stack = _exc_guard + 0x2000;
SECTIONS
{
  .vectors : { KEEP(*(.vectors)) } > FLASH
  .irq_handlers : { KEEP(*(.irq_handlers)) } > FLASH
  .text : { *(.text .text.*) *(.rodata .rodata.*) } > FLASH
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
