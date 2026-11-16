/* Copyright 2026 the kmicro authors (NOTICE).
 * SPDX-License-Identifier: Apache-2.0 */
/* The external interrupts of the QEMU start code: IRQ5_Handler is defined here and runs; interrupt 6 has no handler
 * and ends in the fault report, which names it. (Before the vector table had these entries, the core took the
 * vector of an external interrupt from the code after the table.)
 * On a Cortex-M the two are external interrupts of the NVIC. On QEMU virt and mps3-an536, whose start code has the
 * same handler names for the interrupts of the GIC, they are two of the interrupts that software raises. There a
 * third one is raised too, number 40: the interrupts of the machine's devices, from 32 on, go through another part
 * of the GIC than those of the core, and IRQ40_Handler must run as well. */
#include "kmicro.h"

static volatile int s_ran, s_device;

void IRQ5_Handler(void) { s_ran++; }
void IRQ40_Handler(void) { s_device++; }

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

#if __ARM_ARCH_PROFILE != 'M'
static void pend_device(unsigned n)
{
    volatile uint32_t *gicd = (volatile uint32_t *)(__ARM_ARCH_PROFILE == 'A' ? 0x08000000 : 0xF0000000);
    gicd[0x100 / 4 + n / 32] = 1u << n % 32;        /* GICD_ISENABLERn: enable it */
    gicd[0x200 / 4 + n / 32] = 1u << n % 32;        /* GICD_ISPENDRn: pend it */
    __asm volatile("dsb\n isb");
}
#endif

int main(void)
{
    pend(5);
    kmicro_puts(s_ran == 1 ? "IRQ5_Handler ran\n" : "IRQ5_Handler did not run\n");
#if __ARM_ARCH_PROFILE != 'M'
    pend_device(40);
    kmicro_puts(s_device == 1 ? "IRQ40_Handler ran\n" : "IRQ40_Handler did not run\n");
#endif
    pend(6);
    kmicro_puts("interrupt 6 returned\n");
    return 1;
}
