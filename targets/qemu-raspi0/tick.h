/* Copyright 2026 the kmicro authors (NOTICE).
 * SPDX-License-Identifier: Apache-2.0 */
/* The periodic interrupt of the tests that need one, on this target (targets/qemu-l475/tick.h says what a tick.h
 * gives): the system timer of the BCM2835, a counter of microseconds with four compare registers. Number 1 is used
 * here (0 and 2 belong to the chip's graphics processor); its interrupt is number 1 of the interrupt controller.
 *
 * That timer is not periodic. It interrupts when the low word of its counter equals a compare register and goes on
 * asking until the match is cleared, so the entry in the start code's table, IRQ1_Handler, is defined here: it
 * clears the match, moves the compare value one period on and then calls the test's TICK_HANDLER.
 *
 * tick_start() takes cycles of the 4 MHz clock of QEMU's STM32L475, as on that target, so a test interrupts its
 * program as often here as there, to the microsecond: four of those cycles are one count of this timer. */
#ifndef TICK_H
#define TICK_H
#include <stdint.h>

#define TICK_HANDLER tick_handler
void tick_handler(void);

#define TICK_CS  (*(volatile uint32_t *)0x20003000u)            /* the matches: a 1 written to a bit clears it */
#define TICK_CLO (*(volatile uint32_t *)0x20003004u)            /* the counter, its low word */
#define TICK_C1  (*(volatile uint32_t *)0x20003010u)            /* compare register 1 */

static uint32_t tick_period;            /* in microseconds */

void IRQ1_Handler(void)
{
    TICK_CS = 1u << 1;
    TICK_C1 += tick_period;
    tick_handler();
}

static inline void tick_start(uint32_t cycles)
{
    tick_period = cycles / 4u;
    TICK_C1 = TICK_CLO + tick_period;
    *(volatile uint32_t *)0x2000B210u = 1u << 1;                /* the controller's enable register 1: interrupt 1 on */
}

static inline void tick_stop(void)
{
    *(volatile uint32_t *)0x2000B21Cu = 1u << 1;                /* its disable register 1 */
    TICK_CS = 1u << 1;
}

#endif
