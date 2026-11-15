/* Copyright 2026 the kmicro authors (NOTICE).
 * SPDX-License-Identifier: Apache-2.0 */
/* An interrupt between an exclusive load and its store: the store must fail, so that the code tries again. The
 * atomics of Kotlin and of the runtime are such pairs on every core that has the instructions, and this is what
 * makes them atomic against a handler that changes the same variable in between. A Cortex-M ends the pair itself
 * when it takes an exception; on a Cortex-A the interrupt entry of the start code has to (clrex).
 * The interrupt is number 5 of the start code's handlers, raised as tests/qbuild/irq.c raises it. */
#include "kmicro.h"

static volatile int s_ran;
static uint32_t s_word = 7;

void IRQ5_Handler(void) { s_ran++; }

int main(void)
{
#if defined(__ARM_FEATURE_LDREX) && (__ARM_FEATURE_LDREX & 4)
#if __ARM_ARCH_PROFILE == 'M'
    *(volatile uint32_t *)0xE000E100 = 1u << 5;         /* NVIC_ISER0: enable it */
    volatile uint32_t *raise = (volatile uint32_t *)0xE000E200;     /* NVIC_ISPR0: pend it */
    uint32_t how = 1u << 5;
#else
    volatile uint32_t *raise = (volatile uint32_t *)0x08000F00;     /* GICD_SGIR: raise it, for this core */
    uint32_t how = 2u << 24 | 5u;
#endif
    uint32_t value, failed;
    __asm volatile("ldrex %0, [%2]\n"
                   "str %4, [%3]\n"
                   "dsb\n"
                   "isb\n"
                   "nop\n"
                   "nop\n"
                   "strex %1, %0, [%2]\n"
                   : "=&r"(value), "=&r"(failed) : "r"(&s_word), "r"(raise), "r"(how) : "memory");
    kmicro_puts("handler calls between the exclusive load and the store: ");
    kmicro_put_int(s_ran);
    kmicro_puts(failed ? "; the store failed  OK\n" : "; the store succeeded  BROKEN\n");
    return s_ran == 1 && failed ? 0 : 1;
#else
    kmicro_puts("this core has no exclusive load and store\n");
    return 0;
#endif
}
