/* Copyright 2026 the kmicro authors (NOTICE).
 * SPDX-License-Identifier: Apache-2.0 */
/* Bare-metal start for QEMU's versatilepb machine, an ARM Versatile/PB with an ARM926EJ-S (ARMv5TEJ): exception
 * vectors, a stack per mode, .data/.bss init, MMU null and stack guards, an interrupt entry for the board's
 * interrupt controller, init_array, main, semihosting output, exit and clocks, a fault report. The program runs in
 * Supervisor mode, the mode the core starts in, with the MMU on and a flat map.
 *
 * All of it is ARM code, and the assembly keeps to the instructions of ARMv4T: no cps, no blx, no clz. So the same
 * file is the start code of the ARMv4T model that QEMU puts into this machine (qbuild --target versatilepb-v4t).
 * Its layout follows targets/qemu-raspi0, the start code of an ARMv6 core. */
#include <stdint.h>
#include <string.h>
#include "kmicro.h"

extern uint32_t _estack, _sidata, _sdata, _edata, _sbss, _ebss, _sguard, _eguard;
extern uint32_t _sram, _ttb, _ttb2, _ttb3, _irq_guard, _exc_guard;
extern void (*__init_array_start[])(void), (*__init_array_end[])(void);
int main(void);
void kmicro_exit(int code);
void vectors(void);

#define ENTRY __attribute__((naked, used))
#define NULL_GUARD (1u << 20)                                   /* the first megabyte of the address space */
#define HIGH_VECTORS 0xFFFF0000u                                /* where the core looks for them with SCTLR.V */
#define VIC_IRQSTATUS (*(volatile uint32_t *)0x10140000u)      /* the interrupt controller of the board, a PL190 */

/* The exception vectors. Before ARMv6 a core has no register for their address: they are at address 0, or at
 * 0xFFFF0000 when SCTLR.V is set. Address 0 belongs to the null guard, so the MMU maps the page of this section at
 * the high address too (mmu_guards). The code runs there at another address than it is linked for, so each vector
 * loads the address of its entry from the words behind the vectors, in the same page, where a branch would miss.
 * QEMU enters the image here too (ENTRY in versatilepb.ld), as a reset does. */
__attribute__((section(".vectors"))) ENTRY void vectors(void)
{
    __asm volatile("ldr pc, 1f\n"
                   "ldr pc, 1f + 4\n"
                   "ldr pc, 1f + 8\n"
                   "ldr pc, 1f + 12\n"
                   "ldr pc, 1f + 16\n"
                   "b .\n"                                      /* reserved */
                   "ldr pc, 1f + 20\n"
                   "ldr pc, 1f + 24\n"
                   "1: .word Reset_Handler, undefined_entry, svc_entry, prefetch_abort_entry, data_abort_entry\n"
                   ".word irq_entry, fiq_entry\n");
}

/* Each mode has its own stack pointer. IRQ mode gets a stack for the handlers; FIQ, Abort and Undefined mode share
 * one, since each of them ends in the fault report. lr is set to 0xFFFFFFFF, the address of no function, where a
 * stack trace and the search for an exception handler end. Until the MMU is on (mmu_guards) there are no vectors:
 * an exception in the code before that is lost. */
ENTRY void Reset_Handler(void)
{
    __asm volatile("msr cpsr_c, #0xD1\n"                        /* FIQ mode, interrupts masked */
                   "ldr sp, =_exc_stack\n"
                   "msr cpsr_c, #0xD2\n"                        /* IRQ */
                   "ldr sp, =_irq_stack\n"
                   "msr cpsr_c, #0xD7\n"                        /* Abort */
                   "ldr sp, =_exc_stack\n"
                   "msr cpsr_c, #0xDB\n"                        /* Undefined */
                   "ldr sp, =_exc_stack\n"
                   "msr cpsr_c, #0xD3\n"                        /* Supervisor: the program's mode */
                   "ldr sp, =_estack\n"
                   "mvn lr, #0\n"                               /* no return address: a stack walk ends here */
                   "ldr r0, =start_c\n"
                   "bx r0\n"
                   ".ltorg\n");
}

/* The MMU, with a flat map, for guards without access that turn silent memory corruption into a fault report. The
 * first-level table has an entry for each megabyte of the 4 GB; a section is readable and writable.
 * What the machine has is mapped: its RAM, 128 MB as QEMU gives it, and the megabytes of its peripherals. Every
 * other address is a translation fault. On the board an access there is an external abort, but QEMU's model of it
 * lets such an access pass and reads 0.
 * Guard 0, address 0: the first megabyte is not mapped. The machine has RAM there, so reading a null object or a
 * null C pointer would return data instead of faulting. That is why the vectors are at the high address.
 * Guard 1: the 4 KB between .bss and the stack (versatilepb.ld). An overflowing stack faults there before it writes
 * .bss, which holds the Kotlin heap and the runtime's globals. A function whose frame is larger than the guard
 * could step over it without writing into it (targets/qemu-l475/start.c has the sizes). The megabyte the RAM lies
 * in has a second-level table of 4 KB pages for this, which also leaves a page below each of the two exception
 * stacks unmapped.
 * The last megabyte has a second-level table too, with one page: the vectors, at 0xFFFF0000.
 * The table entries are those of ARMv4 and ARMv5: a page has four parts with a permission each (all AP = 11 here),
 * and bit 4 of a first-level entry is 1.
 * SCTLR.A is set with the MMU: a load or store of a word or halfword at an address that is not a multiple of its
 * size then faults. Without it these cores read the aligned word and rotate it, which is not what any code means;
 * the compiler makes no such access (tests/qbuild/unaligned.c checks the setting). */
static void mmu_guards(void)
{
    uint32_t *l1 = &_ttb, *l2 = &_ttb2, *high = &_ttb3;
    uint32_t ram = (uint32_t)&_sram;                            /* versatilepb.ld: at the start of a megabyte */
    for (uint32_t i = 0; i < 4096u; i++)
        l1[i] = 0;
    for (uint32_t i = 1; i < 128u; i++)                         /* the RAM, without its first megabyte */
        l1[i] = (i << 20) | 0xC12u;                             /* section, AP = 11 (read and write), domain 0 */
    l1[0x100] = 0x10000000u | 0xC12u;                           /* the peripherals: the system registers, */
    l1[0x101] = 0x10100000u | 0xC12u;                           /* the interrupt controller, the timers, the UARTs */
    for (uint32_t i = 0; i < 256u; i++) {
        l2[i] = (ram + (i << 12)) | 0xFF2u;                     /* small page, AP = 11 */
        high[i] = 0;
    }
    l2[((uint32_t)&_sguard - ram) >> 12] = 0;
    l2[((uint32_t)&_irq_guard - ram) >> 12] = 0;
    l2[((uint32_t)&_exc_guard - ram) >> 12] = 0;
    l1[ram >> 20] = (uint32_t)l2 | 0x11u;                       /* a second-level table, domain 0 */
    high[(HIGH_VECTORS >> 12) & 0xFFu] = (uint32_t)&vectors | 0xFF2u;   /* versatilepb.ld: at the start of a page */
    l1[HIGH_VECTORS >> 20] = (uint32_t)high | 0x11u;
    uint32_t sctlr;
    __asm volatile("mcr p15, 0, %1, c2, c0, 0\n"                /* the translation table base */
                   "mcr p15, 0, %3, c3, c0, 0\n"                /* domain access control: domain 0 checks permissions */
                   "mcr p15, 0, %2, c8, c7, 0\n"                /* invalidate the TLBs */
                   "mrc p15, 0, %0, c1, c0, 0\n"                /* the control register (SCTLR) */
                   "orr %0, %0, #0x2000\n"                      /* V: the vectors at 0xFFFF0000 */
                   "orr %0, %0, #3\n"                           /* A: unaligned accesses fault; M: the MMU on */
                   "mcr p15, 0, %0, c1, c0, 0\n"
                   "nop\n"
                   "nop\n"
                   : "=&r"(sctlr) : "r"(l1), "r"(0u), "r"(1u) : "memory");
    (void)sctlr;
}

/* main in a function of its own: whatever LTO inlines into it, start_c keeps a small frame, so clearing .bss can
 * never clear start_c's own stack. */
__attribute__((noinline)) static int run_main(void) { return main(); }

__attribute__((noinline, used, noreturn)) void start_c(void)
{
    memcpy(&_sdata, &_sidata, (size_t)((char *)&_edata - (char *)&_sdata));
    memset(&_sbss, 0, (size_t)((char *)&_ebss - (char *)&_sbss));
    mmu_guards();
    /* The core takes IRQs from here on, as a Cortex-M does from its reset: those a program enables in the interrupt
     * controller, where none is enabled yet. FIQ stays masked: nothing here handles it. */
    uint32_t cpsr;
    __asm volatile("mrs %0, cpsr\n bic %0, %0, #0x80\n msr cpsr_c, %0" : "=&r"(cpsr));
    (void)cpsr;
    for (void (**f)(void) = __init_array_start; f < __init_array_end; f++)
        (*f)();
    kmicro_exit(run_main());
    for (;;) {
    }
}

/* ---- faults: a report, then exit 99 ----
 * Each entry runs in the mode of its exception, on the stack that mode shares with the two other fault modes: it
 * sets the stack pointer again, since a report never returns. It passes on what the mode banks: lr, which is the
 * address of the faulting instruction plus an offset per exception, and the SPSR, the CPSR of the faulting code.
 * The stack pointer and lr of that code are banked in its own mode, so the entry visits that mode to read them;
 * r4 to r7 are the same registers in every mode. tools/symbolize.py resolves the report's "at 0x..." address. */
enum { UNDEFINED = 1, SVC = 2, PREFETCH_ABORT = 3, DATA_ABORT = 4, FIQ = 7 };               /* the vector's index */
typedef struct { uint32_t vector, lr, spsr, sp_usr, lr_usr; } fault_t;

#define FAULT_ENTRY(name, vector)                                                                              \
    ENTRY void name(void)                                                                                      \
    {                                                                                                          \
        __asm volatile("ldr sp, =_exc_stack\n"                                                                 \
                       "mov r4, #" #vector "\n"                                                                \
                       "b fault_entry\n"                                                                       \
                       ".ltorg\n");                                                                            \
    }
FAULT_ENTRY(undefined_entry, 1)
FAULT_ENTRY(svc_entry, 2)
FAULT_ENTRY(prefetch_abort_entry, 3)
FAULT_ENTRY(data_abort_entry, 4)
FAULT_ENTRY(fiq_entry, 7)

ENTRY void fault_entry(void)
{
    __asm volatile("mov r5, lr\n"
                   "mrs r6, spsr\n"
                   "mrs r7, cpsr\n"
                   "and r0, r6, #0x1F\n"
                   "cmp r0, #0x10\n"                            /* User mode has the registers of System mode, */
                   "moveq r0, #0x1F\n"                          /* from which there is a way back */
                   "orr r0, r0, #0xC0\n"                        /* IRQ and FIQ stay masked */
                   "msr cpsr_c, r0\n"
                   "mov r1, sp\n"
                   "mov r2, lr\n"
                   "msr cpsr_c, r7\n"
                   "push {r1, r2}\n"                            /* fault_t, from its end */
                   "push {r4, r5, r6}\n"
                   "mov r0, sp\n"
                   "sub sp, sp, #4\n"                           /* 8-byte alignment for the C code */
                   "bl start_fault\n");                         /* never returns */
}

static void put_hex(const char *label, uint32_t v)
{
    char b[11] = "0x";
    for (int i = 0; i < 8; i++) {
        unsigned d = (v >> (28 - 4 * i)) & 0xFu;
        b[2 + i] = (char)(d < 10u ? '0' + d : 'a' + d - 10u);
    }
    b[10] = 0;
    kmicro_puts(label);
    kmicro_puts(b);
}

static int within(uintptr_t a, uintptr_t lo, uintptr_t hi) { return a >= lo && a < hi; }

__attribute__((used, noreturn)) void start_fault(const fault_t *f)
{
    static const char *const names[] = { 0, "undefined instruction", "SVC", "prefetch abort", "data abort", 0, 0,
                                         "FIQ" };
    static const uint8_t back[] = { 0, 4, 4, 4, 8, 0, 4, 4 };  /* lr minus this is the instruction (ARM state) */
    uint32_t fsr, far;
    __asm volatile("mrc p15, 0, %0, c5, c0, 0\n"
                   "mrc p15, 0, %1, c6, c0, 0\n" : "=&r"(fsr), "=&r"(far));
    int thumb = (f->spsr & 0x20u) != 0u;
    /* In Thumb state lr is 2 less far for an undefined instruction or an SVC, and as in ARM state for the others. */
    uint32_t pc = f->lr - back[f->vector] + (thumb && f->vector <= SVC ? 2u : 0u);
    uintptr_t gs = (uintptr_t)&_sguard, ge = (uintptr_t)&_eguard, ig = (uintptr_t)&_irq_guard;
    uint32_t mode = f->spsr & 0x1Fu;
    /* Only an access to memory that is not mapped is one of the guards: a translation fault, of a section (status
     * 5) or of a page (7). These cores have no register for the address of a prefetch abort: it is the address of
     * the instruction, and one in the null guard is a call through a null pointer. */
    int data = f->vector == DATA_ABORT && ((fsr & 0xDu) == 0x5u);
    int overflow = data && (within(far, gs, ge) || within(far, ig, ig + 4096u)          /* a store into a guard */
                            || (mode != 0x12u && within(f->sp_usr, (uintptr_t)&_sram, ge))  /* SP in it or past it */
                            || (mode == 0x12u && f->sp_usr < ig + 4096u));
    int null_access = (data && far < NULL_GUARD)                                         /* a load or store */
                      || (f->vector == PREFETCH_ABORT && pc < NULL_GUARD);              /* a call through null */
    const char *kind = overflow ? "stack overflow" : null_access ? "null pointer access" : 0;
    kmicro_puts("kmicro fault: ");
    if (kind) {
        kmicro_puts(kind);
        kmicro_puts(" (");
    }
    kmicro_puts(names[f->vector]);
    if (f->vector == FIQ)
        kmicro_puts(" without a handler");
    if (kind)
        kmicro_puts(")");
    put_hex(" at ", pc);
    put_hex("\n    sp ", f->sp_usr);
    put_hex("  lr ", f->lr_usr);
    put_hex("  cpsr ", f->spsr);
    put_hex("  dfsr ", fsr);
    put_hex("  dfar ", far);
    kmicro_puts("\n");
    kmicro_exit(99);
    for (;;) {
    }
}

/* ---- interrupts ----
 * The core has one vector for all of them, and the interrupt controller says which ones are asking. The entry saves
 * what a handler may change and the interrupted code still needs: r0-r3, r12 and lr. A Cortex-M saves these itself
 * when it takes an exception; here nothing does, and a handler, Kotlin or C, is compiled to use them freely. (The
 * code is built without an FPU, so there are no FPU registers to save.)
 * The handler runs in IRQ mode, on that mode's stack, with IRQs masked: handlers do not nest, and the mode is how
 * the runtime knows that a handler is running (runtime/km_cpu.h). These cores have no exclusive loads and stores:
 * the atomics mask interrupts (runtime/atomic32.c), and the entry has nothing to clear. */
ENTRY void irq_entry(void)
{
    __asm volatile("sub lr, lr, #4\n"                           /* the instruction to return to */
                   "push {r0-r3, r12, lr}\n"
                   "mov r0, lr\n"
                   "bl start_irq\n"
                   "ldm sp!, {r0-r3, r12, pc}^\n");             /* and the CPSR back from the SPSR */
}

/* The handlers: IRQ0_Handler to IRQ31_Handler, numbered as the PL190 numbers its 32 inputs (4 is the first pair of
 * timers, 12 the first UART). A program defines the ones it uses, in C or in Kotlin (--c-api), and enables them in
 * the controller. One that is enabled without a handler ends in a fault report, which names its number. The table
 * is in a section of its own, where tools/isr_check.py finds the handlers: nothing else in the image says that
 * these functions are called from an interrupt. */
static void irq_unhandled(void) {}
#define IRQ(n) void IRQ##n##_Handler(void) __attribute__((weak, alias("irq_unhandled")));
#define IRQ10(t) IRQ(t##0) IRQ(t##1) IRQ(t##2) IRQ(t##3) IRQ(t##4) IRQ(t##5) IRQ(t##6) IRQ(t##7) IRQ(t##8) IRQ(t##9)
#define IRQS IRQ(0) IRQ(1) IRQ(2) IRQ(3) IRQ(4) IRQ(5) IRQ(6) IRQ(7) IRQ(8) IRQ(9) IRQ10(1) IRQ10(2) IRQ(30) IRQ(31)
IRQS
#undef IRQ
#define IRQ(n) IRQ##n##_Handler,

__attribute__((section(".irq_handlers"), used))
void (*const irq_handlers[32])(void) = { IRQS };

/* The controller's status register has a bit for each input that is asking and enabled. The lowest number is
 * served; its handler makes the peripheral stop asking, and another one that asks interrupts again as soon as this
 * one has returned. (The vectored interrupts of the PL190, with their priorities, are not used.) */
__attribute__((used)) void start_irq(uint32_t pc)
{
    uint32_t asking = VIC_IRQSTATUS, n = 0;
    if (!asking)                                                /* none after all: it was withdrawn */
        return;
    while (!(asking >> n & 1u))
        n++;
    if (irq_handlers[n] == irq_unhandled) {
        kmicro_puts("kmicro fault: interrupt ");
        kmicro_put_int((int32_t)n);
        put_hex(" without a handler at ", pc);
        kmicro_puts("\n");
        kmicro_exit(99);
    }
    irq_handlers[n]();
}

/* ARM semihosting (QEMU -semihosting): the call is an SVC, with this number in ARM state. It is made in Supervisor
 * mode, whose lr an SVC that is taken would change: lr counts as changed. */
static int semi(int op, void *arg)
{
    register int r0 __asm("r0") = op;
    register void *r1 __asm("r1") = arg;
    __asm volatile("svc 0x123456" : "+r"(r0) : "r"(r1) : "memory", "lr");
    return r0;
}
void kmicro_puts(const char *s) { semi(0x04, (void *)s); }     /* SYS_WRITE0 */
void kmicro_exit(int code)
{
    uint32_t args[2] = { 0x20026u, (uint32_t)code };          /* ADP_Stopped_ApplicationExit, exit code */
    semi(0x20, args);                                           /* SYS_EXIT_EXTENDED */
    for (;;) {
    }
}

/* ---- clocks for kotlin.time and kotlin.random (the hooks in kmicro.h): the host's clocks through semihosting, so
 * the timers stay free for the program ---- */
int64_t kmicro_time_ns(void)
{
    static uint32_t s_hz;
    uint32_t t[2];
    if (s_hz == 0u)
        s_hz = (uint32_t)semi(0x31, 0);                         /* SYS_TICKFREQ */
    if (s_hz == 0u || s_hz == 0xFFFFFFFFu || semi(0x30, t) != 0)   /* SYS_ELAPSED */
        kmicro_panic("semihosting SYS_ELAPSED / SYS_TICKFREQ failed");
    uint64_t ticks = (uint64_t)t[1] << 32 | t[0];
    return (int64_t)(ticks / s_hz * 1000000000u + ticks % s_hz * 1000000000u / s_hz);
}

int64_t kmicro_wall_time_ns(void)
{
    static int64_t s_offset;                                    /* wall clock minus monotonic clock, taken once */
    if (s_offset == 0)
        s_offset = (int64_t)(uint32_t)semi(0x11, 0) * 1000000000 - kmicro_time_ns();   /* SYS_TIME: whole seconds */
    return s_offset + kmicro_time_ns();
}

uint64_t kmicro_random_seed(void) { return (uint64_t)kmicro_time_ns(); }   /* a different Random.Default each run */
