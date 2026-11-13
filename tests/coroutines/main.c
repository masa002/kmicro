/* A coroutine resumed by events from C: 300 suspend/resume cycles (coroutines.kt). */
#include "kmicro.h"

void k_start(void);                             /* Kotlin: @CName("k_start") fun start() */
int32_t k_event(int32_t t);                     /* Kotlin: @CName("k_event") fun event(t: Int): Int */

int main(void)
{
    kmicro_init();
    k_start();                                    /* runs until the first awaitButton() suspends */
    int32_t expect = 0, got = 0, bad = 0;
    for (int32_t i = 1; i <= 300; i++) {          /* 300 button presses, each resumes the coroutine once */
        expect += i;
        got = k_event(i);
        if (got != expect)
            bad++;
    }
    kmicro_stats_t st;
    kmicro_stats(&st);
    kmicro_puts("coroutine: presses sum = "); kmicro_put_int(got);
    kmicro_puts(" expect "); kmicro_put_int(expect);
    kmicro_puts("  gcs="); kmicro_put_int((int32_t)st.gc_count);
    kmicro_puts(" allocs="); kmicro_put_int((int32_t)st.alloc_count);
    kmicro_puts(bad == 0 ? "  OK\n" : "  WRONG\n");
    return bad;
}
