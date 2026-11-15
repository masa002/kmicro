/* Copyright 2026 the kmicro authors (NOTICE).
 * SPDX-License-Identifier: Apache-2.0 */
/* The external interrupts of the QEMU start code: IRQ5_Handler is defined here and runs; interrupt 6 has no handler
 * and ends in the fault report, which names it. (Before the vector table had these entries, the core took the
 * vector of an external interrupt from the code after the table.) */
#include "kmicro.h"

static volatile int s_ran;

void IRQ5_Handler(void) { s_ran++; }

static void pend(unsigned n)
{
    *(volatile uint32_t *)0xE000E100 = 1u << n;     /* NVIC_ISER0: enable it */
    *(volatile uint32_t *)0xE000E200 = 1u << n;     /* NVIC_ISPR0: pend it */
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
