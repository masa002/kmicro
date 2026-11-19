/* Copyright 2026 the kmicro authors (NOTICE).
 * SPDX-License-Identifier: Apache-2.0 */
/* Bare-metal start for QEMU's mps3-an536 machine, a Cortex-R52 (ARMv8-R, AArch32): the way from Hyp mode to
 * Supervisor mode, exception vectors, a stack per mode, VFP on, .data/.bss init, the MPU, the interrupt controller
 * and an interrupt entry, init_array, main, semihosting output, exit and clocks, a fault report.
 *
 * The program is Thumb-2 code, as on a Cortex-M. The core takes every exception in ARM state (SCTLR.TE is 0 after
 * reset), so the vectors and the entries below are ARM code: target("arm"). targets/qemu-virt/start.c is the same
 * for a Cortex-A, with an MMU; what the two share is written alike. */
#include <stdint.h>
#include <string.h>
#include "kmicro.h"

extern uint32_t _estack, _sidata, _sdata, _edata, _sbss, _ebss, _sguard, _eguard;
extern uint32_t _sflash, _eflash, _sram, _irq_guard, _irq_stack, _exc_guard, _exc_stack;
extern void (*__init_array_start[])(void), (*__init_array_end[])(void);
int main(void);
void kmicro_exit(int code);

#define ARM_ENTRY __attribute__((naked, target("arm"), used))
#define NULL_GUARD (1u << 16)                                   /* the first 64 KB of the address space */
#define GICD_CTLR     (*(volatile uint32_t *)0xF0000000u)      /* the GIC (version 3) of the machine: distributor */
#define GICD_TYPER    (*(volatile uint32_t *)0xF0000004u)
#define GICD_IGROUPR  ((volatile uint32_t *)0xF0000080u)
#define GICR_WAKER    (*(volatile uint32_t *)0xF0100014u)      /* and the redistributor of this core */
#define GICR_IGROUPR0 (*(volatile uint32_t *)0xF0110080u)

/* The exception vectors of Supervisor mode and the modes below it: VBAR points here, and QEMU enters the image here
 * too (ENTRY in an536.ld), as a reset does. */
__attribute__((section(".vectors"))) ARM_ENTRY void vectors(void)
{
    __asm volatile("b Reset_Handler\n"
                   "b undefined_entry\n"
                   "b svc_entry\n"
                   "b prefetch_abort_entry\n"
                   "b data_abort_entry\n"
                   "b .\n"                                      /* not used below Hyp mode */
                   "b irq_entry\n"
                   "b fiq_entry\n");
}

/* The vectors of Hyp mode (HVBAR). The program never asks for anything there, so every entry is a fault. */
ARM_ENTRY void hyp_vectors(void)
{
    __asm volatile("b hyp_entry\n b hyp_entry\n b hyp_entry\n b hyp_entry\n"
                   "b hyp_entry\n b hyp_entry\n b hyp_entry\n b hyp_entry\n");
}

/* A Cortex-R52 leaves reset in Hyp mode (EL2). The program runs one level below, in Supervisor mode, for the sake
 * of its interrupt handlers: an exception that is taken to Hyp mode is handled in Hyp mode, the mode the
 * interrupted code is in, and the runtime tells a handler from thread code by the mode (runtime/km_cpu.h). So the
 * reset entry sets up what Hyp mode decides for the level below (nothing is trapped or routed to it, the FPU and
 * the system registers of the interrupt controller are open, the virtual timer counts as the physical one) and
 * returns to the rest of the entry in Supervisor mode.
 * From there on as on a Cortex-A: each mode has its own stack pointer. IRQ mode gets a stack for the handlers; FIQ,
 * Abort and Undefined mode share one, since each of them ends in the fault report. Then the vectors, and VFP and
 * NEON before any compiled C code runs: with LTO, main and the Kotlin code it calls can be inlined into the C
 * start function, whose prologue then saves FP registers (vpush). lr is set to 0xFFFFFFFF, the address of no
 * function, where a stack trace and the search for an exception handler end.
 * qbuild also runs code built for a Cortex-R5 on this machine (ARMv7-R, which the Cortex-R52 runs). The start code
 * is then compiled for that core, which has no Hyp mode: its instructions are let in by hand. */
ARM_ENTRY void Reset_Handler(void)
{
    __asm volatile(".arch_extension virt\n"
                   "mrs r0, cpsr\n"
                   "and r0, r0, #0x1F\n"
                   "cmp r0, #0x1A\n"                            /* Hyp mode? */
                   "bne 1f\n"
                   "ldr r0, =hyp_vectors\n"
                   "mcr p15, 4, r0, c12, c0, 0\n"               /* HVBAR */
                   "mov r0, #0\n"
                   "mcr p15, 4, r0, c1, c1, 0\n"                /* HCR = 0: no trap, no interrupt routed to Hyp mode */
                   "mcrr p15, 4, r0, r0, c14\n"                 /* CNTVOFF = 0 */
                   "movw r0, #0x33FF\n"
                   "mcr p15, 4, r0, c1, c1, 2\n"                /* HCPTR: the FPU is not trapped */
                   "mov r0, #0xF\n"
                   "mcr p15, 4, r0, c12, c9, 5\n"               /* ICC_HSRE: the GIC's system registers, below too */
                   "adr r0, 1f\n"
                   "msr elr_hyp, r0\n"
                   "movw r0, #0x1D3\n"                          /* Supervisor mode, interrupts masked, ARM state */
                   "msr spsr_hyp, r0\n"
                   "eret\n"
                   "1:\n"
                   "cpsid aif, #0x11\n"                         /* FIQ mode, interrupts masked */
                   "ldr sp, =_exc_stack\n"
                   "cps #0x12\n"                                /* IRQ */
                   "ldr sp, =_irq_stack\n"
                   "cps #0x17\n"                                /* Abort */
                   "ldr sp, =_exc_stack\n"
                   "cps #0x1B\n"                                /* Undefined */
                   "ldr sp, =_exc_stack\n"
                   "cps #0x13\n"                                /* Supervisor: the program's mode */
                   "ldr sp, =_estack\n"
                   "ldr r0, =vectors\n"
                   "mcr p15, 0, r0, c12, c0, 0\n");             /* VBAR */
#if defined(__ARM_FP)
    __asm volatile("mrc p15, 0, r0, c1, c0, 2\n"                /* CPACR */
                   "orr r0, r0, #0x00F00000\n"                  /* CP10/CP11 full access (VFP, NEON) */
                   "mcr p15, 0, r0, c1, c0, 2\n"
                   "isb\n"
                   "mov r0, #0x40000000\n"                      /* FPEXC.EN */
                   "vmsr fpexc, r0\n");
#endif
    __asm volatile("mvn lr, #0\n"                               /* no return address: a stack walk ends here */
                   "ldr r0, =start_c\n"
                   "bx r0\n"
                   ".ltorg\n");
}

/* The MPU of ARMv8-R gives a region a base and a limit, in steps of 64 bytes, and has no permission that refuses a
 * privileged read. So nothing is refused: the regions say what the program has, the default map behind them is
 * turned off (SCTLR.BR), and an access anywhere else faults. That makes the guards:
 * Address 0: the machine has RAM there, so reading a null object or a null C pointer would return data. No region
 * covers it, nor any other address that is not listed here.
 * The 4 KB between .bss and the stack (an536.ld): the RAM is two regions, below and above it. An overflowing stack
 * faults there before it writes .bss, which holds the Kotlin heap and the runtime's globals. A function whose
 * frame is larger than the guard could step over it without writing into it (targets/qemu-l475/start.c has the
 * sizes). The two exception stacks are regions of their own, each with 4 KB of nothing below it.
 * The code and the constants are read-only, and nothing but them can be executed. */
static void mpu_region(uint32_t n, uint32_t base, uint32_t end, uint32_t access, uint32_t attr)
{
    __asm volatile("mcr p15, 0, %0, c6, c2, 1\n"                /* PRSELR */
                   "mcr p15, 0, %1, c6, c3, 0\n"                /* PRBAR: base, access */
                   "mcr p15, 0, %2, c6, c3, 1\n"                /* PRLAR: the last 64 bytes, attributes, enable */
                   : : "r"(n), "r"(base | access), "r"(((end - 64u) & ~63u) | attr << 1 | 1u) : "memory");
}

static void mpu_guards(void)
{
    enum { CODE = 4, DATA = 1, MEMORY = 0, DEVICE = 1 };        /* read-only; read, write, no execute; MAIR0 index */
    uint32_t irq = (uint32_t)&_irq_guard + 4096u, exc = (uint32_t)&_exc_guard + 4096u, sctlr;
    __asm volatile("mcr p15, 0, %0, c10, c2, 0" : : "r"(0x04FFu));     /* MAIR0: 0 normal memory, 1 device */
    mpu_region(0u, (uint32_t)&_sflash, (uint32_t)&_eflash, CODE, MEMORY);
    mpu_region(1u, (uint32_t)&_sram, (uint32_t)&_sguard, DATA, MEMORY);
    mpu_region(2u, (uint32_t)&_eguard, (uint32_t)&_estack, DATA, MEMORY);
    mpu_region(3u, irq, (uint32_t)&_irq_stack, DATA, MEMORY);
    mpu_region(4u, exc, (uint32_t)&_exc_stack, DATA, MEMORY);
    mpu_region(5u, 0xE0000000u, 0u, DATA, DEVICE);              /* the machine's peripherals, up to the top */
    __asm volatile("mrc p15, 0, %0, c1, c0, 0\n"                /* SCTLR */
                   "bic %0, %0, #0x20000\n"                     /* BR off: no default map behind the regions */
                   "orr %0, %0, #1\n"                           /* M: the MPU on */
                   "mcr p15, 0, %0, c1, c0, 0\n"
                   "isb\n" : "=&r"(sctlr) : : "memory");
    (void)sctlr;
}

/* The interrupt controller passes on what a program enables in it, at any priority, as interrupts of group 1,
 * which the core takes as IRQs. Every interrupt is put into that group: after reset each is in group 0, which is
 * not turned on here and would arrive as an FIQ. The core's own interrupts (0 to 31) have their group in the
 * redistributor, those of the machine's devices (32 and up) in the distributor, 32 to a register, as many as
 * GICD_TYPER says. The controller's interface to the core is system registers, not memory. */
static void gic_on(void)
{
    GICR_WAKER &= ~2u;                                          /* this core is awake */
    while (GICR_WAKER & 4u) {
    }
    GICR_IGROUPR0 = 0xFFFFFFFFu;
    for (uint32_t i = 1u; i <= (GICD_TYPER & 0x1Fu); i++)
        GICD_IGROUPR[i] = 0xFFFFFFFFu;
    GICD_CTLR = 0x12u;                                          /* ARE, group 1 on */
    __asm volatile("mcr p15, 0, %0, c12, c12, 5\n"              /* ICC_SRE: the system registers */
                   "isb\n"
                   "mcr p15, 0, %1, c4, c6, 0\n"                /* ICC_PMR: every priority */
                   "mcr p15, 0, %2, c12, c12, 7\n"              /* ICC_IGRPEN1: group 1 to the core */
                   "isb\n" : : "r"(7u), "r"(0xFFu), "r"(1u) : "memory");
}

/* main in a function of its own: whatever LTO inlines into it, start_c keeps a small frame, so clearing .bss can
 * never clear start_c's own stack. */
__attribute__((noinline)) static int run_main(void) { return main(); }

__attribute__((noinline, used, noreturn)) void start_c(void)
{
    memcpy(&_sdata, &_sidata, (size_t)((char *)&_edata - (char *)&_sdata));
    memset(&_sbss, 0, (size_t)((char *)&_ebss - (char *)&_sbss));
    mpu_guards();
    gic_on();
    __asm volatile("cpsie i");                                  /* IRQs from here on, as a Cortex-M from its reset */
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
 * r3 to r7 are the same registers in every mode. An SVC of the program is taken in the program's own mode,
 * Supervisor mode: there is no other mode to visit. Its stack pointer is the one the entry had before it set its
 * own, kept in r3, and its lr is gone, because the exception wrote the return address over it: the report says
 * "lr unknown". tools/symbolize.py resolves the report's "at 0x..." address. */
enum { UNDEFINED = 1, SVC = 2, PREFETCH_ABORT = 3, DATA_ABORT = 4, FIQ = 7 };               /* the vector's index */
typedef struct { uint32_t vector, lr, spsr, sp_usr, lr_usr; } fault_t;

#define FAULT_ENTRY(name, vector)                                                                              \
    ARM_ENTRY void name(void)                                                                                  \
    {                                                                                                          \
        __asm volatile("mov r3, sp\n"                                                                          \
                       "ldr sp, =_exc_stack\n"                                                                 \
                       "mov r4, #" #vector "\n"                                                                \
                       "b fault_entry\n"                                                                       \
                       ".ltorg\n");                                                                            \
    }
FAULT_ENTRY(undefined_entry, 1)
FAULT_ENTRY(svc_entry, 2)
FAULT_ENTRY(prefetch_abort_entry, 3)
FAULT_ENTRY(data_abort_entry, 4)
FAULT_ENTRY(fiq_entry, 7)

ARM_ENTRY void fault_entry(void)
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
                   "eor r0, r6, r7\n"
                   "tst r0, #0x1F\n"                            /* the faulting code ran in this very mode: */
                   "moveq r1, r3\n"                             /* its sp, as the entry found it */
                   "push {r1, r2}\n"                            /* fault_t, from its end */
                   "push {r4, r5, r6}\n"
                   "mov r0, sp\n"
                   "sub sp, sp, #4\n"                           /* 8-byte alignment for the C code */
                   "bl start_fault\n");                         /* never returns */
}

ARM_ENTRY void hyp_entry(void)
{
    __asm volatile(".arch_extension virt\n"
                   "ldr sp, =_exc_stack\n"
                   "mrc p15, 4, r0, c5, c2, 0\n"                /* HSR: why */
                   "mrs r1, elr_hyp\n"                          /* and where */
                   "bl start_hyp_fault\n"                       /* never returns */
                   ".ltorg\n");
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
    uint32_t dfsr, dfar, ifsr, ifar;
    __asm volatile("mrc p15, 0, %0, c5, c0, 0\n"
                   "mrc p15, 0, %1, c6, c0, 0\n"
                   "mrc p15, 0, %2, c5, c0, 1\n"
                   "mrc p15, 0, %3, c6, c0, 2\n" : "=&r"(dfsr), "=&r"(dfar), "=&r"(ifsr), "=&r"(ifar));
    int thumb = (f->spsr & 0x20u) != 0u;
    /* In Thumb state lr is 2 less far for an undefined instruction or an SVC, and as in ARM state for the others. */
    uint32_t pc = f->lr - back[f->vector] + (thumb && f->vector <= SVC ? 2u : 0u);
    uintptr_t gs = (uintptr_t)&_sguard, ge = (uintptr_t)&_eguard, ig = (uintptr_t)&_irq_guard;
    uint32_t mode = f->spsr & 0x1Fu, cpsr;
    __asm volatile("mrs %0, cpsr" : "=r"(cpsr));
    int lr_lost = mode == (cpsr & 0x1Fu);                       /* the exception was taken in the code's own mode */
    /* Only an access that no region of the MPU covers is one of the guards. With this MPU the status is in the long
     * format (bit 9), and such an access is a translation fault (status 4) or, as QEMU reports it, a permission
     * fault (12), both of level 0. A breakpoint is a prefetch abort too, with another status and no address. */
    int data = f->vector == DATA_ABORT && ((dfsr & 0x237u) == 0x204u);
    int prefetch = f->vector == PREFETCH_ABORT && ((ifsr & 0x237u) == 0x204u);
    int overflow = data && (within(dfar, gs, ge) || within(dfar, ig, ig + 4096u)        /* a store into a guard */
                            || (mode != 0x12u && within(f->sp_usr, (uintptr_t)&_sram, ge))  /* SP in it or past it */
                            || (mode == 0x12u && f->sp_usr < ig + 4096u));
    int null_access = (data && dfar < NULL_GUARD)                                        /* a load or store */
                      || (prefetch && ifar < NULL_GUARD);                                /* a call through null */
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
    if (lr_lost)
        kmicro_puts("  lr unknown");
    else
        put_hex("  lr ", f->lr_usr);
    put_hex("  cpsr ", f->spsr);
    put_hex("  dfsr ", dfsr);
    put_hex("  dfar ", dfar);
    put_hex("  ifsr ", ifsr);
    put_hex("  ifar ", ifar);
    kmicro_puts("\n");
    kmicro_exit(99);
    for (;;) {
    }
}

__attribute__((used, noreturn)) void start_hyp_fault(uint32_t hsr, uint32_t pc)
{
    put_hex("kmicro fault: an exception taken to Hyp mode at ", pc);
    put_hex("\n    hsr ", hsr);
    kmicro_puts("\n");
    kmicro_exit(99);
    for (;;) {
    }
}

/* ---- interrupts ----
 * The core has one vector for all of them, and the interrupt controller says which one came. The entry saves what a
 * handler may change and the interrupted code still needs: r0-r3, r12 and lr, and with an FPU the registers that no
 * function has to keep (d0-d7, d16-d31) and the FPSCR. A Cortex-M saves these itself when it takes an exception;
 * here nothing does, and a handler, Kotlin or C, is compiled to use them freely.
 * The handler runs in IRQ mode, on that mode's stack, with IRQs masked: handlers do not nest, and the mode is how
 * the runtime knows that a handler is running (runtime/km_cpu.h). clrex before the return: the atomics are
 * exclusive loads and stores, and the store of the interrupted code must fail after a handler ran (the test
 * qbuild_exclusive). */
ARM_ENTRY void irq_entry(void)
{
    __asm volatile("sub lr, lr, #4\n"                           /* the instruction to return to */
                   "push {r0-r3, r12, lr}\n"
                   "mov r0, lr\n"
#if defined(__ARM_FP)
                   "vpush {d0-d7}\n"
#if defined(__ARM_NEON)
                   "vpush {d16-d31}\n"
#endif
                   "vmrs r1, fpscr\n"
                   "push {r1, r2}\n"                            /* r2: 8-byte alignment for the C code */
#endif
                   "bl start_irq\n"
#if defined(__ARM_FP)
                   "pop {r1, r2}\n"
                   "vmsr fpscr, r1\n"
#if defined(__ARM_NEON)
                   "vpop {d16-d31}\n"
#endif
                   "vpop {d0-d7}\n"
#endif
                   "clrex\n"
                   "ldm sp!, {r0-r3, r12, pc}^\n");             /* and the CPSR back from the SPSR */
}

/* The handlers: IRQ0_Handler to IRQ99_Handler, numbered as the GIC numbers its interrupts (0 to 15 are raised by
 * software, 16 to 31 are the core's own, such as its timers, and the machine's devices start at 32). A program
 * defines the ones it uses, in C or in Kotlin (--c-api). One that is enabled without a handler ends in a fault
 * report, which names its number. The table is in a section of its own, where tools/isr_check.py finds the handlers:
 * nothing else in the image says that these functions are called from an interrupt. */
static void irq_unhandled(void) {}
#define IRQ(n) void IRQ##n##_Handler(void) __attribute__((weak, alias("irq_unhandled")));
#define IRQ10(t) IRQ(t##0) IRQ(t##1) IRQ(t##2) IRQ(t##3) IRQ(t##4) IRQ(t##5) IRQ(t##6) IRQ(t##7) IRQ(t##8) IRQ(t##9)
#define IRQS IRQ(0) IRQ(1) IRQ(2) IRQ(3) IRQ(4) IRQ(5) IRQ(6) IRQ(7) IRQ(8) IRQ(9) \
             IRQ10(1) IRQ10(2) IRQ10(3) IRQ10(4) IRQ10(5) IRQ10(6) IRQ10(7) IRQ10(8) IRQ10(9)
IRQS
#undef IRQ
#define IRQ(n) IRQ##n##_Handler,

__attribute__((section(".irq_handlers"), used))
void (*const irq_handlers[100])(void) = { IRQS };

/* In a section of its own, which the linker script puts between _sirq_entry and _eirq_entry: a handler returns to
 * this function, and by that address the runtime knows a handler from the functions a handler calls
 * (runtime/km_cpu.h). */
__attribute__((used, section(".irq_entry"))) void start_irq(uint32_t pc)
{
    uint32_t iar, n;
    __asm volatile("mrc p15, 0, %0, c12, c12, 0" : "=r"(iar));  /* ICC_IAR1: acknowledge it: its number */
    n = iar & 0xFFFFFFu;
    if (n >= 1020u)                                             /* none after all: it was withdrawn */
        return;
    if (n >= 100u || irq_handlers[n] == irq_unhandled) {
        kmicro_puts("kmicro fault: interrupt ");
        kmicro_put_int((int32_t)n);
        put_hex(" without a handler at ", pc);
        kmicro_puts("\n");
        kmicro_exit(99);
    }
    irq_handlers[n]();
    __asm volatile("mcr p15, 0, %0, c12, c12, 1" : : "r"(iar)); /* ICC_EOIR1: done, the next one may come */
}

/* ARM semihosting (QEMU -semihosting): on the A and R profiles the call is an SVC, with this number in Thumb state. */
static int semi(int op, void *arg)
{
    register int r0 __asm("r0") = op;
    register void *r1 __asm("r1") = arg;
    __asm volatile("svc 0xAB" : "+r"(r0) : "r"(r1) : "memory");
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
