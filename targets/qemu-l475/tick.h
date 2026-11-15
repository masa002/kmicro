/* Copyright 2026 the kmicro authors (NOTICE).
 * SPDX-License-Identifier: Apache-2.0 */
/* The periodic interrupt of the tests that need one, on this target: SysTick, the timer of every Cortex-M core.
 * Each QEMU target that has such an interrupt has a tick.h, and qbuild puts the target's folder on the include
 * path, so the C driver of a test is the same on every target:
 *
 *   void TICK_HANDLER(void) { ... }    the handler, in the one C file that includes this header
 *   tick_start(n);                     an interrupt every n cycles of the timer's clock
 *   tick_stop();
 *
 * The clock is the core's, as the machine starts it: 4 MHz on QEMU's STM32L475, where 4000 cycles are 1 ms. */
#ifndef TICK_H
#define TICK_H
#include <stdint.h>

#define TICK_HANDLER SysTick_Handler    /* the vector table of start.c calls it */

static inline void tick_start(uint32_t cycles)
{
    *(volatile uint32_t *)0xE000E014 = cycles - 1u;     /* LOAD */
    *(volatile uint32_t *)0xE000E018 = 0;               /* VAL */
    *(volatile uint32_t *)0xE000E010 = 7u;              /* CTRL: processor clock, interrupt, enable */
}

static inline void tick_stop(void) { *(volatile uint32_t *)0xE000E010 = 0; }

#endif
