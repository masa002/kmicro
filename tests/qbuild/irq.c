/* Copyright 2026 the kmicro authors (NOTICE).
 * SPDX-License-Identifier: Apache-2.0 */
/* The external interrupts of the QEMU start code: IRQ5_Handler is defined here and runs; interrupt 6 has no handler
 * and ends in the fault report, which names it. (Before the vector table had these entries, the core took the
 * vector of an external interrupt from the code after the table.)
 * On a Cortex-M the two are external interrupts of the NVIC. On QEMU virt and mps3-an536, whose start code has the
 * same handler names for the interrupts of the GIC, they are two of the interrupts that software raises. */
#include "kmicro.h"

static volatile int s_ran;

void IRQ5_Handler(void) { s_ran++; }

static void pend(unsigned n)
{
#if __ARM_ARCH_PROFILE == 'M'
    *(volatile uint32_t *)0xE000E100 = 1u << n;     /* NVIC_ISER0: enable it */
    *(volatile uint32_t *)0xE000E200 = 1u << n;     /* NVIC_ISPR0: pend it */
#elif __ARM_ARCH_PROFILE == 'A'
    *(volatile uint32_t *)0x08000F00 = 2u << 24 | n;    /* GICD_SGIR: raise it, for this core */
#else
    *(volatile uint32_t *)0xF0110100 = 1u << n;         /* GICR_ISENABLER0 of a GIC v3: enable it */
    __asm volatile("mcrr p15, 0, %0, %1, c12" : : "r"(n << 24 | 1u), "r"(0u));  /* ICC_SGI1R: raise it, for this core */
#endif
    __asm volatile("dsb\n isb");
}

int main(void)
{
    pend(5);
    kmicro_puts(s_ran == 1 ? "IRQ5_Handler ran\n" : "IRQ5_Handler did not run\n");
    pend(6);
    kmicro_puts("interrupt 6 returned\n");
    return 1;
}
