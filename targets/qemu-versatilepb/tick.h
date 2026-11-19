/* Copyright 2026 the kmicro authors (NOTICE).
 * SPDX-License-Identifier: Apache-2.0 */
/* The periodic interrupt of the tests that need one, on this target (targets/qemu-l475/tick.h says what a tick.h
 * gives): the first timer of the board, an SP804, in its periodic mode. It counts down at 1 MHz and interrupts at
 * 0, through input 4 of the interrupt controller. The entry in the start code's table, IRQ4_Handler, is defined
 * here: it clears the timer's interrupt and then calls the test's TICK_HANDLER.
 *
 * tick_start() takes cycles of the 4 MHz clock of QEMU's STM32L475, as on that target, so a test interrupts its
 * program as often here as there, to the microsecond: four of those cycles are one count of this timer. */
#ifndef TICK_H
#define TICK_H
#include <stdint.h>

#define TICK_HANDLER tick_handler
void tick_handler(void);

#define TICK_LOAD    (*(volatile uint32_t *)0x101E2000u)
#define TICK_CONTROL (*(volatile uint32_t *)0x101E2008u)
#define TICK_INTCLR  (*(volatile uint32_t *)0x101E200Cu)

void IRQ4_Handler(void)
{
    TICK_INTCLR = 1u;
    tick_handler();
}

static inline void tick_start(uint32_t cycles)
{
    TICK_LOAD = cycles / 4u - 1u;
    TICK_CONTROL = 0xE2u;                                       /* enabled, periodic, with its interrupt, 32 bits */
    *(volatile uint32_t *)0x10140010u = 1u << 4;                /* the controller's enable register: input 4 on */
}

static inline void tick_stop(void)
{
    TICK_CONTROL = 0;
    TICK_INTCLR = 1u;
    *(volatile uint32_t *)0x10140014u = 1u << 4;                /* its enable-clear register */
}

#endif
