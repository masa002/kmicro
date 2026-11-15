/* Copyright 2026 the kmicro authors (NOTICE).
 * SPDX-License-Identifier: Apache-2.0 */
/* The periodic interrupt of the tests that need one, on this target (targets/qemu-l475/tick.h says what a tick.h
 * gives): the virtual timer of the core, one of the ARM generic timers, whose interrupt is number 27 of the GIC.
 *
 * That timer is not periodic. It interrupts when its counter reaches a compare value and goes on asking until the
 * value is changed, so the entry in the start code's table, IRQ27_Handler, is defined here: it moves the compare
 * value one period on and then calls the test's TICK_HANDLER.
 *
 * QEMU's timer counts at 62.5 MHz. tick_start() takes cycles of the 4 MHz clock of QEMU's STM32L475, as on that
 * target, so a test interrupts its program as often here as there. */
#ifndef TICK_H
#define TICK_H
#include <stdint.h>

#define TICK_HANDLER tick_handler
void tick_handler(void);

static uint32_t tick_period;            /* in counts of the timer */

static inline uint64_t tick_read64(void)                        /* CNTVCT, the counter */
{
    uint32_t lo, hi;
    __asm volatile("mrrc p15, 1, %0, %1, c14" : "=r"(lo), "=r"(hi));
    return (uint64_t)hi << 32 | lo;
}

static inline void tick_compare(uint64_t at)                    /* CNTV_CVAL, the compare value */
{
    __asm volatile("mcrr p15, 3, %0, %1, c14" : : "r"((uint32_t)at), "r"((uint32_t)(at >> 32)));
}

static inline uint64_t tick_compared(void)
{
    uint32_t lo, hi;
    __asm volatile("mrrc p15, 3, %0, %1, c14" : "=r"(lo), "=r"(hi));
    return (uint64_t)hi << 32 | lo;
}

void IRQ27_Handler(void)
{
    tick_compare(tick_compared() + tick_period);
    tick_handler();
}

static inline void tick_start(uint32_t cycles)
{
    tick_period = (uint32_t)((uint64_t)cycles * 125u / 8u);     /* 62.5 MHz / 4 MHz */
    tick_compare(tick_read64() + tick_period);
    __asm volatile("mcr p15, 0, %0, c14, c3, 1" : : "r"(1u));   /* CNTV_CTL: enable, interrupt not masked */
    *(volatile uint32_t *)0x08000100u = 1u << 27;               /* GICD_ISENABLER0: interrupt 27 on */
}

static inline void tick_stop(void)
{
    __asm volatile("mcr p15, 0, %0, c14, c3, 1" : : "r"(0u));
    *(volatile uint32_t *)0x08000180u = 1u << 27;               /* GICD_ICENABLER0 */
}

#endif
