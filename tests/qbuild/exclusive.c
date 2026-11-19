/* Copyright 2026 the kmicro authors (NOTICE).
 * SPDX-License-Identifier: Apache-2.0 */
/* An interrupt between an exclusive load and its store: the store must fail, so that the code tries again. The
 * atomics of Kotlin and of the runtime are such pairs on every core that has the instructions, and this is what
 * makes them atomic against a handler that changes the same variable in between. A Cortex-M ends the pair itself
 * when it takes an exception; on a Cortex-A the interrupt entry of the start code has to (clrex).
 * The interrupt is number 5 of the start code's handlers, raised as tests/qbuild/irq.c raises it; on QEMU raspi0
 * it is number 29, which a store to the mini UART raises, as that file says. */
#include "kmicro.h"

static volatile int s_ran;
static uint32_t s_word = 7;

#if defined(__ARM_ARCH_PROFILE)
void IRQ5_Handler(void) { s_ran++; }
#else                                                   /* QEMU raspi0 */
void IRQ29_Handler(void)
{
    *(volatile uint32_t *)0x20215044 = 0;               /* AUX_MU_IER: the mini UART stops asking */
    s_ran++;
}
#endif

int main(void)
{
#if defined(__ARM_FEATURE_LDREX) && (__ARM_FEATURE_LDREX & 4)
#if __ARM_ARCH_PROFILE == 'M'
    *(volatile uint32_t *)0xE000E100 = 1u << 5;         /* NVIC_ISER0: enable it */
    volatile uint32_t *raise = (volatile uint32_t *)0xE000E200;     /* NVIC_ISPR0: pend it */
    uint32_t how = 1u << 5;
#elif __ARM_ARCH_PROFILE == 'A'
    volatile uint32_t *raise = (volatile uint32_t *)0x08000F00;     /* GICD_SGIR: raise it, for this core */
    uint32_t how = 2u << 24 | 5u;
#elif __ARM_ARCH_PROFILE == 'R'
    *(volatile uint32_t *)0xF0110100 = 1u << 5;         /* GICR_ISENABLER0 of a GIC v3: enable it */
    uint32_t raise = 0, how = 5u << 24 | 1u;            /* ICC_SGI1R, a system register: raise it, for this core */
#define RAISE "mcrr p15, 0, %4, %3, c12\n"
#else
    *(volatile uint32_t *)0x2000B210 = 1u << 29;        /* the enable register 1 of the BCM2835: interrupt 29 on */
    *(volatile uint32_t *)0x20215004 = 1u;              /* AUX_ENABLES: the mini UART on */
    volatile uint32_t *raise = (volatile uint32_t *)0x20215044;     /* AUX_MU_IER: its interrupts on */
    uint32_t how = 3u;
#endif
#ifndef RAISE
#define RAISE "str %4, [%3]\n"
#endif
#if defined(__ARM_ARCH_PROFILE)
#define BARRIERS "dsb\n isb\n"
#else
#define BARRIERS                                        /* instructions of ARMv7 and of the M profile */
#endif
    uint32_t value, failed;
    __asm volatile("ldrex %0, [%2]\n"
                   RAISE
                   BARRIERS
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
