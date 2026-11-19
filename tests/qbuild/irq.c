/* Copyright 2026 the kmicro authors (NOTICE).
 * SPDX-License-Identifier: Apache-2.0 */
/* The external interrupts of the QEMU start code: IRQ5_Handler is defined here and runs; interrupt 6 has no handler
 * and ends in the fault report, which names it. (Before the vector table had these entries, the core took the
 * vector of an external interrupt from the code after the table.)
 * On a Cortex-M the two are external interrupts of the NVIC. On QEMU virt and mps3-an536, whose start code has the
 * same handler names for the interrupts of the GIC, they are two of the interrupts that software raises. There a
 * third one is raised too, number 40: the interrupts of the machine's devices, from 32 on, go through another part
 * of the GIC than those of the core, and IRQ40_Handler must run as well.
 * The interrupt controller of QEMU raspi0 raises nothing by itself. There the two are interrupts that a store to
 * their peripheral raises, and the output has their numbers: with a handler the one of the mini UART (29), whose
 * transmitter asks as soon as its interrupt is enabled, and without one that of the UART (57), which asks once it
 * has sent a character. */
#include "kmicro.h"

static volatile int s_ran, s_device;

void IRQ5_Handler(void) { s_ran++; }
void IRQ40_Handler(void) { s_device++; }

#if !defined(__ARM_ARCH_PROFILE)                    /* QEMU raspi0 */
#define RAN "IRQ29_Handler ran\n"
#define NOT_RUN "IRQ29_Handler did not run\n"
#define RETURNED "interrupt 57 returned\n"

void IRQ29_Handler(void)
{
    *(volatile uint32_t *)0x20215044 = 0;           /* AUX_MU_IER: the mini UART stops asking */
    s_ran++;
}

static void pend(unsigned n)
{
    if (n == 5) {
        *(volatile uint32_t *)0x2000B210 = 1u << 29;    /* the controller's enable register 1: interrupt 29 on */
        *(volatile uint32_t *)0x20215004 = 1u;          /* AUX_ENABLES: the mini UART on */
        *(volatile uint32_t *)0x20215044 = 3u;          /* AUX_MU_IER: its interrupts on */
    } else {
        *(volatile uint32_t *)0x2000B214 = 1u << (57 - 32);     /* enable register 2: interrupt 57 on */
        *(volatile uint32_t *)0x20201038 = 1u << 5;     /* the UART's interrupt mask: its transmit interrupt on */
        *(volatile uint32_t *)0x20201000 = '\n';        /* its data register: a character to send */
    }
}
#else
#define RAN "IRQ5_Handler ran\n"
#define NOT_RUN "IRQ5_Handler did not run\n"
#define RETURNED "interrupt 6 returned\n"

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
#endif

#if __ARM_ARCH_PROFILE == 'A' || __ARM_ARCH_PROFILE == 'R'
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
    kmicro_puts(s_ran == 1 ? RAN : NOT_RUN);
#if __ARM_ARCH_PROFILE == 'A' || __ARM_ARCH_PROFILE == 'R'
    pend_device(40);
    kmicro_puts(s_device == 1 ? "IRQ40_Handler ran\n" : "IRQ40_Handler did not run\n");
#endif
    pend(6);
    kmicro_puts(RETURNED);
    return 1;
}
