/* The garbage collector: 6000 objects through a small heap, survivors in locals, a global and an array (gc.kt).
 * run_all runs it with a 16 KB and a 5 KB heap. */
#include "kmicro.h"

int32_t k_gc(int32_t rounds);                   /* Kotlin: @CName("k_gc") fun gc(rounds: Int): Int */

int main(void)
{
    kmicro_init();
    const int32_t rounds = 60;
    int32_t expect = rounds * 4950;                          /* garbage chains: 0..99 per round */
    expect += rounds * (rounds - 1) / 2;                     /* keep chain: 0..rounds-1 */
    for (int32_t r = 0; r < rounds; r += 7) expect += r * 1000;   /* global chain */
    expect += 50 * 49 / 2;                                   /* the array */
    int32_t got = k_gc(rounds);
    kmicro_stats_t st;
    kmicro_stats(&st);
    kmicro_puts("gc test: sum="); kmicro_put_int(got);
    kmicro_puts(" expect="); kmicro_put_int(expect);
    kmicro_puts("  heap="); kmicro_put_int((int32_t)st.heap_bytes);
    kmicro_puts(" allocs="); kmicro_put_int((int32_t)st.alloc_count);
    kmicro_puts(" gcs="); kmicro_put_int((int32_t)st.gc_count);
    kmicro_puts(" freed="); kmicro_put_int((int32_t)st.objects_freed);
    kmicro_puts(" peak="); kmicro_put_int((int32_t)st.peak_bytes);
    kmicro_puts(got == expect ? "  OK\n" : "  WRONG\n");
    return got == expect ? 0 : 1;
}
