/* Copyright 2026 the kmicro authors (NOTICE).
 * SPDX-License-Identifier: Apache-2.0 */
/* The things the runtime asks the core itself, which the architecture profiles answer in different ways: mask
 * interrupts for a few instructions, tell a handler from the thread code, and tell the return address of a handler
 * from one into a handler. C and C++. */
#ifndef KM_CPU_H
#define KM_CPU_H
#include <stdint.h>

#if defined(__ARM_ARCH_PROFILE) && __ARM_ARCH_PROFILE == 'M'

/* Short critical sections against interrupt handlers: PRIMASK is saved and restored, never just enabled. */
static inline uint32_t km_irq_save(void)
{
    uint32_t pm;
    __asm volatile("mrs %0, primask\n cpsid i" : "=r"(pm) : : "memory");
    return pm;
}
static inline void km_irq_restore(uint32_t pm) { __asm volatile("msr primask, %0" : : "r"(pm) : "memory"); }

/* 0 in thread code, else the exception number of the running handler (IPSR). */
static inline uint32_t km_handler(void)
{
    uint32_t ipsr;
    __asm volatile("mrs %0, ipsr" : "=r"(ipsr));
    return ipsr & 0x1FFu;
}

/* True when `ra`, the return address of a function, is the one a handler itself returns to: the function was then
 * inlined into the handler, and `ra` names no code of the program. On this profile it is an EXC_RETURN value. */
static inline int km_handler_return(uintptr_t ra) { return ra >= 0xF0000000u; }

#elif defined(__ARM_ARCH_PROFILE)                    /* 'A' and 'R': Cortex-A (AArch32) and Cortex-R */

/* The same with the I and F bits of the CPSR: FIQ handlers may run Kotlin code too. The saved value is the CPSR's
 * control byte; the mode in it is the one this code runs in. */
static inline uint32_t km_irq_save(void)
{
    uint32_t cpsr;
    __asm volatile("mrs %0, cpsr\n cpsid if" : "=r"(cpsr) : : "memory");
    return cpsr;
}
static inline void km_irq_restore(uint32_t cpsr) { __asm volatile("msr cpsr_c, %0" : : "r"(cpsr) : "memory"); }

/* There is no IPSR. A handler is code that runs in the mode its exception is taken in: FIQ (0x11), IRQ (0x12),
 * Abort (0x17) or Undefined (0x1B); the result is that mode, and 0 in every other mode. So thread code runs in
 * Supervisor or System mode, and a board's interrupt entry calls the handler without leaving IRQ or FIQ mode
 * (docs/porting.md): an entry that changes to System mode to let interrupts nest hides its handlers from the
 * runtime's guards. A handler of SVC runs in Supervisor mode and is not told from thread code. */
static inline uint32_t km_handler(void)
{
    uint32_t cpsr;
    __asm volatile("mrs %0, cpsr" : "=r"(cpsr));
    uint32_t mode = cpsr & 0x1Fu;
    return mode == 0x11u || mode == 0x12u || mode == 0x17u || mode == 0x1Bu ? mode : 0u;
}

/* A handler is called like any other function, by the interrupt entry of the start code, so the address it returns
 * to lies in that entry. The linker script says where that is, with these two symbols around the code that calls
 * the handlers (targets/qemu-virt/virt.ld, docs/porting.md). In an image without them both are 0 and the result is
 * always 0: a panic then names the entry where it would name the handler. */
extern const char _sirq_entry[] __attribute__((weak)), _eirq_entry[] __attribute__((weak));
static inline int km_handler_return(uintptr_t ra)
{
    return ra - (uintptr_t)_sirq_entry < (uintptr_t)_eirq_entry - (uintptr_t)_sirq_entry;
}

#else                                                /* not ARM: no interrupts to mask, never a handler */

static inline uint32_t km_irq_save(void) { return 0; }
static inline void km_irq_restore(uint32_t saved) { (void)saved; }
static inline uint32_t km_handler(void) { return 0; }
static inline int km_handler_return(uintptr_t ra) { (void)ra; return 0; }

#endif

#endif
