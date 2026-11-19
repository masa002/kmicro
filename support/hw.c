/* Copyright 2026 the kmicro authors (NOTICE).
 * SPDX-License-Identifier: Apache-2.0 */
/* hw.c - see hw.h. Compiled by clang -flto together with the Kotlin code, so each body is inlined at the call. */
#include "hw.h"

uint32_t hw_rd32(uint32_t addr) { return *(volatile uint32_t *)addr; }
void     hw_wr32(uint32_t addr, uint32_t v) { *(volatile uint32_t *)addr = v; }
uint16_t hw_rd16(uint32_t addr) { return *(volatile uint16_t *)addr; }
void     hw_wr16(uint32_t addr, uint16_t v) { *(volatile uint16_t *)addr = v; }
uint8_t  hw_rd8(uint32_t addr) { return *(volatile uint8_t *)addr; }
void     hw_wr8(uint32_t addr, uint8_t v) { *(volatile uint8_t *)addr = v; }

/* Any alignment: the packed view makes clang emit an access that works at any address on the core it compiles for
 * (a plain LDR/STR from ARMv7-M on; single bytes on ARMv6-M and ARMv8-M Baseline, where an unaligned LDR faults),
 * never LDRD/LDM, which would fault on an odd address. */
typedef struct __attribute__((packed)) { uint32_t v; } u32_any;
typedef struct __attribute__((packed)) { uint16_t v; } u16_any;
uint32_t mem_rd32(uint32_t addr) { return ((const u32_any *)addr)->v; }
void     mem_wr32(uint32_t addr, uint32_t v) { ((u32_any *)addr)->v = v; }
uint16_t mem_rd16(uint32_t addr) { return ((const u16_any *)addr)->v; }
void     mem_wr16(uint32_t addr, uint16_t v) { ((u16_any *)addr)->v = v; }
uint8_t  mem_rd8(uint32_t addr) { return *(const uint8_t *)addr; }
void     mem_wr8(uint32_t addr, uint8_t v) { *(uint8_t *)addr = v; }

#if defined(__ARM_ARCH_PROFILE)
void hw_dsb(void) { __asm volatile("dsb" ::: "memory"); }
void hw_isb(void) { __asm volatile("isb" ::: "memory"); }
void hw_dmb(void) { __asm volatile("dmb" ::: "memory"); }
void hw_wfi(void) { __asm volatile("wfi" ::: "memory"); }
#else
/* An ARM core from before the profiles has no such instructions. Where it has the operation, it is a write to
 * CP15: all four on ARMv6 (ARM1176JZF-S); on ARMv5 (ARM926EJ-S) the wait for an interrupt and the drain of the
 * write buffer, which is what hw_dsb() does there. The others do nothing, and on ARMv4T all four do nothing: an
 * ARM7TDMI has no CP15, and hw_wfi() returns at once. */
#define HW_CP15_C7(crm, op2) __asm volatile("mcr p15, 0, %0, c7, " #crm ", " #op2 :: "r"(0u) : "memory")
#if __ARM_ARCH >= 5
void hw_dsb(void) { HW_CP15_C7(c10, 4); }
void hw_wfi(void) { HW_CP15_C7(c0, 4); }
#else
void hw_dsb(void) {}
void hw_wfi(void) {}
#endif
#if __ARM_ARCH >= 6
void hw_isb(void) { HW_CP15_C7(c5, 4); }               /* flush the prefetch buffer */
void hw_dmb(void) { HW_CP15_C7(c10, 5); }
#else
void hw_isb(void) {}
void hw_dmb(void) {}
#endif
#endif
void hw_nop(void) { __asm volatile("nop"); }

#if __ARM_ARCH_PROFILE == 'M'
uint32_t hw_irq_save(void)
{
    uint32_t m;
    __asm volatile("mrs %0, primask\n cpsid i" : "=r"(m) :: "memory");
    return m;
}

void hw_irq_restore(uint32_t primask)
{
    __asm volatile("msr primask, %0" :: "r"(primask) : "memory");
}

uint32_t hw_ipsr(void)
{
    uint32_t r;
    __asm volatile("mrs %0, ipsr" : "=r"(r));
    return r;
}
#else
/* A Cortex-A or Cortex-R core has no PRIMASK, and an ARM core from before the profiles has none: the value is the
 * CPSR, whose I and F bits mask IRQ and FIQ. They have no IPSR, BASEPRI or DWT either: hw_ipsr and the three
 * hw_basepri functions are not defined there, so a program that calls them does not link, and hw_cycles_enable()
 * returns false. */
uint32_t hw_irq_save(void)
{
    uint32_t m;
#if __ARM_ARCH >= 6
    __asm volatile("mrs %0, cpsr\n cpsid if" : "=r"(m) :: "memory");
#else                                               /* no cpsid before ARMv6: the two bits, set in a copy */
    uint32_t masked;
    __asm volatile("mrs %0, cpsr\n orr %1, %0, #0xC0\n msr cpsr_c, %1" : "=&r"(m), "=&r"(masked) :: "memory");
#endif
    return m;
}

void hw_irq_restore(uint32_t cpsr)
{
    __asm volatile("msr cpsr_c, %0" :: "r"(cpsr) : "memory");
}
#endif

/* BASEPRI exists on ARMv7-M and ARMv8-M Mainline (Cortex-M3 and up, M33 and up). On ARMv6-M and ARMv8-M Baseline
 * (Cortex-M0, M0+, M1, M23) these three functions are not defined: a program that calls them does not link there. */
#if __ARM_ARCH_PROFILE == 'M' && __ARM_ARCH_ISA_THUMB == 2
uint32_t hw_basepri(void)
{
    uint32_t r;
    __asm volatile("mrs %0, basepri" : "=r"(r));
    return r;
}

void hw_basepri_set(uint32_t v) { __asm volatile("msr basepri, %0" :: "r"(v) : "memory"); }
void hw_basepri_max(uint32_t v) { __asm volatile("msr basepri_max, %0" :: "r"(v) : "memory"); }
#endif

/* False where hw_cycles() stays 0. The DWT of ARMv6-M and ARMv8-M Baseline (Cortex-M0, M0+, M1, M23) has no cycle
 * counter, a chip can be built without one (DWT_CTRL.NOCYCCNT), and QEMU does not model the DWT: it ignores the
 * writes. Some Cortex-M7 chips keep the DWT locked until its lock access register gets the key; a core without the
 * lock ignores that write. */
bool hw_cycles_enable(void)
{
#if __ARM_ARCH_PROFILE == 'M' && __ARM_ARCH_ISA_THUMB == 2
    *(volatile uint32_t *)0xE000EDFCu |= 1u << 24;    /* CoreDebug->DEMCR.TRCENA: the DWT unit on */
    *(volatile uint32_t *)0xE0001FB0u = 0xC5ACCE55u;  /* DWT->LAR: the key */
    *(volatile uint32_t *)0xE0001004u = 0;            /* DWT->CYCCNT */
    *(volatile uint32_t *)0xE0001000u |= 1u;          /* DWT->CTRL.CYCCNTENA */
    uint32_t ctrl = *(volatile uint32_t *)0xE0001000u;
    return (ctrl & 1u) != 0 && (ctrl & (1u << 25)) == 0;   /* it took the enable bit, and NOCYCCNT is clear */
#else
    return false;
#endif
}

#if __ARM_ARCH_PROFILE == 'M'
uint32_t hw_cycles(void) { return *(volatile uint32_t *)0xE0001004u; }   /* DWT->CYCCNT */
#else
uint32_t hw_cycles(void) { return 0; }
#endif
