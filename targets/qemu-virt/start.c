/* Copyright 2026 the kmicro authors (NOTICE).
 * SPDX-License-Identifier: Apache-2.0 */
/* Bare-metal start for QEMU's virt machine with a Cortex-A7 (ARMv7-A, AArch32): exception vectors, a stack per mode,
 * VFP on, .data/.bss init, MMU null and stack guards, the interrupt controller and an interrupt entry, init_array,
 * main, semihosting output, exit and clocks, a fault report. The program runs in Supervisor mode, the mode the core
 * starts in, with the MMU on and a flat map.
 *
 * The program is Thumb-2 code, as on a Cortex-M. The core takes every exception in ARM state (SCTLR.TE is 0 after
 * reset), so the vectors and the entries below are ARM code: target("arm"). */
#include <stdint.h>
#include <string.h>
#include "kmicro.h"

extern uint32_t _estack, _sidata, _sdata, _edata, _sbss, _ebss, _sguard, _eguard;
extern uint32_t _sram, _ttb, _ttb2, _irq_guard, _exc_guard;
extern void (*__init_array_start[])(void), (*__init_array_end[])(void);
int main(void);
void kmicro_exit(int code);

#define ARM_ENTRY __attribute__((naked, target("arm"), used))
#define NULL_GUARD (1u << 20)                                   /* the first megabyte of the address space */
#define GICD_CTLR (*(volatile uint32_t *)0x08000000u)          /* the GIC (version 2) of the machine: distributor */
#define GICC_CTLR (*(volatile uint32_t *)0x08010000u)          /* and the interface to this core */
#define GICC_PMR  (*(volatile uint32_t *)0x08010004u)
#define GICC_IAR  (*(volatile uint32_t *)0x0801000Cu)
#define GICC_EOIR (*(volatile uint32_t *)0x08010010u)

/* The exception vectors: VBAR points here, and QEMU enters the image here too (ENTRY in virt.ld), as a reset does. */
__attribute__((section(".vectors"))) ARM_ENTRY void vectors(void)
{
    __asm volatile("b Reset_Handler\n"
                   "b undefined_entry\n"
                   "b svc_entry\n"
                   "b prefetch_abort_entry\n"
                   "b data_abort_entry\n"
                   "b .\n"                                      /* a trap to Hyp mode: not used */
                   "b irq_entry\n"
                   "b fiq_entry\n");
}

/* Each mode has its own stack pointer. IRQ mode gets a stack for the handlers; FIQ, Abort and Undefined mode share
 * one, since each of them ends in the fault report. Then the vectors, and VFP and NEON before any compiled C code
 * runs: with LTO, main and the Kotlin code it calls can be inlined into the C start function, whose prologue then
 * saves FP registers (vpush). lr is set to 0xFFFFFFFF, the address of no function, where a stack trace and the
 * search for an exception handler end. */
ARM_ENTRY void Reset_Handler(void)
{
    __asm volatile("cpsid aif, #0x11\n"                         /* FIQ mode, interrupts masked */
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

/* The MMU, with a flat map, for two guards without access that turn silent memory corruption into a fault report.
 * The first-level table maps the 4 GB in sections of 1 MB, each readable and writable.
 * Guard 0, address 0: the first megabyte is not mapped. The machine has flash memory there, so reading a null object
 * or a null C pointer would return data instead of faulting.
 * Guard 1: the 4 KB between .bss and the stack (virt.ld). An overflowing stack faults there before it writes .bss,
 * which holds the Kotlin heap and the runtime's globals. A function whose frame is larger than the guard could step
 * over it without writing into it (targets/qemu-l475/start.c has the sizes). The megabyte the RAM lies in has a
 * second-level table of 4 KB pages for this, which also leaves a page below each of the two exception stacks
 * unmapped. */
static void mmu_guards(void)
{
    uint32_t *l1 = &_ttb, *l2 = &_ttb2;
    uint32_t ram = (uint32_t)&_sram;                            /* virt.ld: at the start of a megabyte */
    for (uint32_t i = 0; i < 4096u; i++)
        l1[i] = (i << 20) | 0xC02u;                             /* section, AP = 11 (read and write), domain 0 */
    l1[0] = 0;
    for (uint32_t i = 0; i < 256u; i++)
        l2[i] = (ram + (i << 12)) | 0x032u;                     /* small page, AP = 11 */
    l2[((uint32_t)&_sguard - ram) >> 12] = 0;
    l2[((uint32_t)&_irq_guard - ram) >> 12] = 0;
    l2[((uint32_t)&_exc_guard - ram) >> 12] = 0;
    l1[ram >> 20] = (uint32_t)l2 | 1u;                          /* a second-level table, domain 0 */
    uint32_t sctlr;
    __asm volatile("mcr p15, 0, %1, c2, c0, 0\n"                /* TTBR0 */
                   "mcr p15, 0, %2, c2, c0, 2\n"                /* TTBCR = 0: TTBR0 maps everything */
                   "mcr p15, 0, %3, c3, c0, 0\n"                /* DACR: domain 0 checks the permissions */
                   "mcr p15, 0, %2, c8, c7, 0\n"                /* TLBIALL */
                   "mrc p15, 0, %0, c1, c0, 0\n"                /* SCTLR */
                   "orr %0, %0, #1\n"                           /* M: the MMU on */
                   "mcr p15, 0, %0, c1, c0, 0\n"
                   "isb\n" : "=&r"(sctlr) : "r"(l1), "r"(0u), "r"(1u) : "memory");
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
    /* The interrupt controller passes on what a program enables in it, at any priority, and the core takes IRQs
     * from here on, as a Cortex-M does from its reset. FIQ stays masked: nothing here handles it. */
    GICD_CTLR = 1u;
    GICC_PMR = 0xFFu;
    GICC_CTLR = 1u;
    __asm volatile("cpsie i");
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
    ARM_ENTRY void name(void)                                                                                  \
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
    uint32_t dfsr, dfar, ifsr, ifar;
    __asm volatile("mrc p15, 0, %0, c5, c0, 0\n"
                   "mrc p15, 0, %1, c6, c0, 0\n"
                   "mrc p15, 0, %2, c5, c0, 1\n"
                   "mrc p15, 0, %3, c6, c0, 2\n" : "=&r"(dfsr), "=&r"(dfar), "=&r"(ifsr), "=&r"(ifar));
    int thumb = (f->spsr & 0x20u) != 0u;
    /* In Thumb state lr is 2 less far for an undefined instruction or an SVC, and as in ARM state for the others. */
    uint32_t pc = f->lr - back[f->vector] + (thumb && f->vector <= SVC ? 2u : 0u);
    uintptr_t gs = (uintptr_t)&_sguard, ge = (uintptr_t)&_eguard, ig = (uintptr_t)&_irq_guard;
    uint32_t mode = f->spsr & 0x1Fu;
    /* Only an access to memory that is not mapped is one of the guards: a translation fault, of a section (status
     * 5) or of a page (7). A breakpoint is a prefetch abort too, with another status and no address. */
    int data = f->vector == DATA_ABORT && ((dfsr & 0x40Du) == 0x005u);
    int prefetch = f->vector == PREFETCH_ABORT && ((ifsr & 0x40Du) == 0x005u);
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

/* ---- interrupts ----
 * The core has one vector for all of them, and the interrupt controller says which one came. The entry saves what a
 * handler may change and the interrupted code still needs: r0-r3, r12 and lr, and with an FPU the registers that no
 * function has to keep (d0-d7, d16-d31) and the FPSCR. A Cortex-M saves these itself when it takes an exception;
 * here nothing does, and a handler, Kotlin or C, is compiled to use them freely.
 * The handler runs in IRQ mode, on that mode's stack, with IRQs masked: handlers do not nest, and the mode is how
 * the runtime knows that a handler is running (runtime/km_cpu.h). clrex before the return: the atomics are
 * exclusive loads and stores, and the store of the interrupted code must fail after a handler ran. The core does
 * not see to that by itself (the test qbuild_exclusive fails without this line). */
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

__attribute__((used)) void start_irq(uint32_t pc)
{
    uint32_t iar = GICC_IAR, n = iar & 0x3FFu;                  /* acknowledge it: its number */
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
    GICC_EOIR = iar;                                            /* done: the controller may send the next one */
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
