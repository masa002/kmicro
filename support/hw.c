/* hw.c - see hw.h. Compiled by clang -flto together with the Kotlin code, so each body is inlined at the call. */
#include "hw.h"

uint32_t hw_rd32(uint32_t addr) { return *(volatile uint32_t *)addr; }
void     hw_wr32(uint32_t addr, uint32_t v) { *(volatile uint32_t *)addr = v; }
uint16_t hw_rd16(uint32_t addr) { return *(volatile uint16_t *)addr; }
void     hw_wr16(uint32_t addr, uint16_t v) { *(volatile uint16_t *)addr = v; }
uint8_t  hw_rd8(uint32_t addr) { return *(volatile uint8_t *)addr; }
void     hw_wr8(uint32_t addr, uint8_t v) { *(volatile uint8_t *)addr = v; }

/* Any alignment: the packed view makes clang emit plain LDR/STR (unaligned-capable on the Cortex-M4), never
 * LDRD/LDM, which would fault on an odd address. */
typedef struct __attribute__((packed)) { uint32_t v; } u32_any;
typedef struct __attribute__((packed)) { uint16_t v; } u16_any;
uint32_t mem_rd32(uint32_t addr) { return ((const u32_any *)addr)->v; }
void     mem_wr32(uint32_t addr, uint32_t v) { ((u32_any *)addr)->v = v; }
uint16_t mem_rd16(uint32_t addr) { return ((const u16_any *)addr)->v; }
void     mem_wr16(uint32_t addr, uint16_t v) { ((u16_any *)addr)->v = v; }
uint8_t  mem_rd8(uint32_t addr) { return *(const uint8_t *)addr; }
void     mem_wr8(uint32_t addr, uint8_t v) { *(uint8_t *)addr = v; }

void hw_dsb(void) { __asm volatile("dsb" ::: "memory"); }
void hw_isb(void) { __asm volatile("isb" ::: "memory"); }
void hw_dmb(void) { __asm volatile("dmb" ::: "memory"); }
void hw_wfi(void) { __asm volatile("wfi" ::: "memory"); }
void hw_nop(void) { __asm volatile("nop"); }

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

/* BASEPRI exists on ARMv7-M and ARMv8-M Mainline (Cortex-M3 and up, M33 and up). On ARMv6-M and ARMv8-M Baseline
 * (Cortex-M0, M0+, M1, M23) these three functions are not defined: a program that calls them does not link there. */
#if __ARM_ARCH_ISA_THUMB == 2
uint32_t hw_basepri(void)
{
    uint32_t r;
    __asm volatile("mrs %0, basepri" : "=r"(r));
    return r;
}

void hw_basepri_set(uint32_t v) { __asm volatile("msr basepri, %0" :: "r"(v) : "memory"); }
void hw_basepri_max(uint32_t v) { __asm volatile("msr basepri_max, %0" :: "r"(v) : "memory"); }
#endif

/* QEMU does not model the DWT: there the writes are ignored and hw_cycles() stays 0. */
void hw_cycles_enable(void)
{
    *(volatile uint32_t *)0xE000EDFCu |= 1u << 24;    /* CoreDebug->DEMCR.TRCENA: the DWT unit on */
    *(volatile uint32_t *)0xE0001004u = 0;            /* DWT->CYCCNT */
    *(volatile uint32_t *)0xE0001000u |= 1u;          /* DWT->CTRL.CYCCNTENA */
}

uint32_t hw_cycles(void) { return *(volatile uint32_t *)0xE0001004u; }   /* DWT->CYCCNT */
