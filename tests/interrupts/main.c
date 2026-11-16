/* Copyright 2026 the kmicro authors (NOTICE).
 * SPDX-License-Identifier: Apache-2.0 */
/* Kotlin code in an interrupt handler: what the runtime refuses, and what works. run_all builds this file once per test
 * case, with one TEST_* macro defined; the handler of the target's periodic interrupt (tick.h) then calls that
 * case's Kotlin function (isr.h). */
#include "kmicro.h"
#include "isr.h"
#include "tick.h"

#ifndef RVR
#define RVR 4000u                       /* the tick's period: 1 ms at the 4 MHz clock QEMU's STM32L475 starts with */
#endif
#ifndef ROUNDS
#define ROUNDS 2000
#endif

static volatile int s_done, s_ticks, s_handled;

void TICK_HANDLER(void)
{
    s_ticks++;
#if defined(TEST_ALLOC)
    if (!s_done) { s_done = 1; alloc_in_handler(s_ticks); }
#elif defined(TEST_TO_STRING)
    if (!s_done) { s_done = 1; to_string_in_handler(12345); }
#elif defined(TEST_GC)
    if (!s_done) { s_done = 1; kmicro_gc(); }
#elif defined(TEST_COLLECT)
    if (!s_done) { s_done = 1; collect_in_handler(); }
#elif defined(TEST_SCHEDULE)
    if (!s_done) { s_done = 1; schedule_gc(); }
#elif defined(TEST_LAZY) || defined(TEST_INIT_ALL)
    if (s_ticks <= 5) read_settings();
    if (s_ticks == 5) s_done = 1;
#elif defined(TEST_THROW)
    s_handled += throw_in_handler();
#elif defined(TEST_SWAP_FIELDS)
    swap_fields();
#elif defined(TEST_SWAP_SLOTS)
    swap_slots();
#elif defined(TEST_COPY)
    copy_read();
#elif defined(TEST_WEAK)
    weak_read();
#elif defined(TEST_CHARS)
    if (s_ticks <= 64) s_handled += classify(s_ticks);
    if (s_ticks == 64) s_done = 1;
#endif
}

static void wait_for_handler(void)
{
    for (volatile int i = 0; i < 50000000 && !s_done; i++) {
    }
    tick_stop();
}

int main(void)
{
    kmicro_init();
    kmicro_stats_t a, b;
#if defined(TEST_SCHEDULE)
    kmicro_stats(&a);
    tick_start(RVR);
    wait_for_handler();
    kmicro_stats(&b);
    kmicro_puts("collections by GC.schedule(): in a handler ");
    kmicro_put_int((int32_t)(b.gc_count - a.gc_count));
    schedule_gc();
    kmicro_stats(&a);
    kmicro_puts(", in thread mode ");
    kmicro_put_int((int32_t)(a.gc_count - b.gc_count));
    kmicro_puts("\n");
    return 0;
#elif defined(TEST_INIT_ALL)
    kt_init_all();                      /* every global of package isr: objects, sub-packages, @ThreadLocal */
    kmicro_stats(&a);
    tick_start(RVR);
    wait_for_handler();
    int32_t settings = read_settings();
    kmicro_stats(&b);
    kmicro_puts("settings ");
    kmicro_put_int(settings);
    kmicro_puts(" after 5 handler calls; allocations after kt_init_all: ");
    kmicro_put_int((int32_t)(b.alloc_count - a.alloc_count));
    kmicro_puts("\n");
    return settings == 258 && b.alloc_count == a.alloc_count ? 0 : 1;
#elif defined(TEST_THROW)
    kt_init_all();                      /* creates the exception the handler throws */
    tick_start(RVR);
    int32_t thrown = 0, caught = 0;
    while (s_ticks < 20 && thrown < 200000) {   /* until 20 handler calls came, most of them during a throw */
        caught += throw_in_thread(500);
        thrown += 500;
    }
    tick_stop();
    int ok = caught == thrown && s_ticks >= 20 && s_handled == s_ticks;
    kmicro_puts("thread code: thrown ");
    kmicro_put_int(thrown);
    kmicro_puts(", caught ");
    kmicro_put_int(caught);
    kmicro_puts("; handler: calls ");
    kmicro_put_int(s_ticks);
    kmicro_puts(", caught ");
    kmicro_put_int(s_handled);
    kmicro_puts(ok ? "  OK\n" : "  BROKEN\n");
    return !ok;
#elif defined(TEST_SWAP_FIELDS) || defined(TEST_SWAP_SLOTS)
    swap_setup();
    tick_start(RVR);
#if defined(TEST_SWAP_FIELDS)
    int32_t bad = check_fields(ROUNDS);
#else
    int32_t bad = check_slots(ROUNDS);
#endif
    tick_stop();
    kmicro_stats(&a);
    kmicro_puts("swapped in ");
    kmicro_put_int(s_ticks);
    kmicro_puts(" handler calls, collections ");
    kmicro_put_int((int32_t)a.gc_count);
    kmicro_puts(", bad reads ");
    kmicro_put_int(bad);
    kmicro_puts(bad == 0 && s_ticks > 100 ? "  OK\n" : "  BROKEN\n");
    return bad != 0 || s_ticks <= 100;
#elif defined(TEST_COPY)
    (void)b;
    int32_t size = copy_setup() - 40;   /* four arrays of 8 */
    tick_start(RVR);
    int32_t torn = copy_rotate(ROUNDS, size / 4);
    tick_stop();
    kmicro_stats(&a);
    kmicro_puts("copied and filled under ");
    kmicro_put_int(s_ticks);
    kmicro_puts(" handler calls, torn elements ");
    kmicro_put_int(torn);
    kmicro_puts(torn == 0 && s_ticks > 100 ? "  OK\n" : "  BROKEN\n");
    return torn != 0 || s_ticks <= 100;
#elif defined(TEST_WEAK)
    (void)b;
    kt_init_all();
    tick_start(RVR);
    int32_t bad = weak_rounds(ROUNDS);
    tick_stop();
    kmicro_stats(&a);
    int ok = bad == 0 && s_ticks > 100 && weak_taken() > 100;
    kmicro_puts("weak references read in ");
    kmicro_put_int(s_ticks);
    kmicro_puts(" handler calls, objects taken ");
    kmicro_put_int(weak_taken());
    kmicro_puts(", collections ");
    kmicro_put_int((int32_t)a.gc_count);
    kmicro_puts(", bad reads ");
    kmicro_put_int(bad);
    kmicro_puts(ok ? "  OK\n" : "  BROKEN\n");
    return !ok;
#elif defined(TEST_CHARS)
    (void)a;
    (void)b;
    tick_start(RVR);                    /* no kt_init_all(): the handler is the first to read the Unicode tables */
    wait_for_handler();
    int32_t sum = 0;
    for (int i = 1; i <= 64; i++)
        sum += classify(i);
    int ok = s_done && s_handled == sum;
    kmicro_puts("64 characters classified by a handler first: checksum ");
    kmicro_put_int(s_handled);
    kmicro_puts(", by the main code afterwards ");
    kmicro_put_int(sum);
    kmicro_puts(ok ? "  OK\n" : "  BROKEN\n");
    return !ok;
#else                                  /* the cases the runtime must stop */
    (void)a;
    (void)b;
    tick_start(RVR);
    wait_for_handler();
    kmicro_puts("the handler returned\n");
    return 1;
#endif
}
