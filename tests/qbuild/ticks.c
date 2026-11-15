/* Copyright 2026 the kmicro authors (NOTICE).
 * SPDX-License-Identifier: Apache-2.0 */
/* qbuild --icount: QEMU's clock is the number of instructions the program has run, so the target's timer (tick.h),
 * which counts that clock, interrupts a loop after the same number of turns each time. On the host's clock that
 * number differs from tick to tick by far more than the one turn the loop's own length allows. */
#include "kmicro.h"
#include "tick.h"

#define TICKS 50

static volatile uint32_t s_turns;       /* counted by the loop in main */
static volatile uint32_t s_at[TICKS + 1];   /* s_turns at each tick */
static volatile int s_ticks;

void TICK_HANDLER(void)
{
    if (s_ticks <= TICKS)
        s_at[s_ticks] = s_turns;
    s_ticks++;
}

int main(void)
{
    kmicro_init();
    tick_start(4000u);
    while (s_ticks <= TICKS)
        s_turns++;
    tick_stop();
    uint32_t least = ~0u, most = 0;
    for (int i = 1; i <= TICKS; i++) {
        uint32_t turns = s_at[i] - s_at[i - 1];
        least = turns < least ? turns : least;
        most = turns > most ? turns : most;
    }
    int ok = most - least <= 1u;
    kmicro_puts("loop turns between two ticks: at least ");
    kmicro_put_int((int32_t)least);
    kmicro_puts(", at most ");
    kmicro_put_int((int32_t)most);
    kmicro_puts(ok ? "  OK\n" : "  BROKEN\n");
    return !ok;
}
