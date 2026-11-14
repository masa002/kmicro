/* Kotlin code in an interrupt handler: what the runtime refuses, and what works. run_all builds this file once per test
 * case, with one TEST_* macro defined; SysTick_Handler then calls that case's Kotlin function (isr.h). */
#include "kmicro.h"
#include "isr.h"

#ifndef RVR
#define RVR 4000u                       /* SysTick reload: 1 ms at the 4 MHz clock QEMU's STM32L475 starts with */
#endif
#ifndef ROUNDS
#define ROUNDS 2000
#endif

static volatile int s_done, s_ticks, s_handled;

void SysTick_Handler(void)
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
#endif
}

static void systick(uint32_t reload)
{
    *(volatile uint32_t *)0xE000E014 = reload - 1u;     /* LOAD */
    *(volatile uint32_t *)0xE000E018 = 0;               /* VAL */
    *(volatile uint32_t *)0xE000E010 = reload ? 7u : 0u;/* CTRL: processor clock, interrupt, enable */
}

static void wait_for_handler(void)
{
    for (volatile int i = 0; i < 50000000 && !s_done; i++) {
    }
    systick(0);
}

int main(void)
{
    kmicro_init();
    kmicro_stats_t a, b;
#if defined(TEST_SCHEDULE)
    kmicro_stats(&a);
    systick(RVR);
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
    kt_init_all();                      /* every global of package isr, objects and sub-packages included */
    kmicro_stats(&a);
    systick(RVR);
    wait_for_handler();
    int32_t settings = read_settings();
    kmicro_stats(&b);
    kmicro_puts("settings ");
    kmicro_put_int(settings);
    kmicro_puts(" after 5 handler calls; allocations after kt_init_all: ");
    kmicro_put_int((int32_t)(b.alloc_count - a.alloc_count));
    kmicro_puts("\n");
    return settings == 48 && b.alloc_count == a.alloc_count ? 0 : 1;
#elif defined(TEST_THROW)
    kt_init_all();                      /* creates the exception the handler throws */
    systick(RVR);
    int32_t thrown = 0, caught = 0;
    while (s_ticks < 20 && thrown < 200000) {   /* until 20 handler calls came, most of them during a throw */
        caught += throw_in_thread(500);
        thrown += 500;
    }
    systick(0);
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
    systick(RVR);
#if defined(TEST_SWAP_FIELDS)
    int32_t bad = check_fields(ROUNDS);
#else
    int32_t bad = check_slots(ROUNDS);
#endif
    systick(0);
    kmicro_stats(&a);
    kmicro_puts("swapped in ");
    kmicro_put_int(s_ticks);
    kmicro_puts(" handler calls, collections ");
    kmicro_put_int((int32_t)a.gc_count);
    kmicro_puts(", bad reads ");
    kmicro_put_int(bad);
    kmicro_puts(bad == 0 && s_ticks > 100 ? "  OK\n" : "  BROKEN\n");
    return bad != 0 || s_ticks <= 100;
#else                                   /* the cases the runtime must stop */
    (void)a;
    (void)b;
    systick(RVR);
    wait_for_handler();
    kmicro_puts("the handler returned\n");
    return 1;
#endif
}
