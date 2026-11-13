/* kmicro self-test: runs every check of selftest.kt and prints PASS / FAIL, then the heap statistics.
 * The exit code is the number of failed checks. */
#include "kmicro.h"
#include "selftest.h"

static int s_fail;

static void report(const char *name, bool ok)
{
    kmicro_puts(ok ? "  PASS  " : "  FAIL  ");
    kmicro_puts(name);
    kmicro_puts("\n");
    if (!ok)
        s_fail++;
}

static void stat(const char *name, uint32_t v)
{
    kmicro_puts(name);
    kmicro_put_int((int32_t)v);
}

/* kmicro_init() runs the module initializers (the compiler registers them through .init_array, which LTO usually
 * resolves at link time). The standard library's modules register their thread-local slots there, so no slot means
 * that no initializer ran. */
static bool runtime_init(void)
{
    kmicro_init();
    return kmicro_tls_slot_count > 0;
}

/* One collection more, and the garbage left by the checks before it is gone. */
static bool full_gc(void)
{
    kmicro_stats_t before, after;
    kmicro_stats(&before);
    kmicro_gc();
    kmicro_stats(&after);
    return after.gc_count == before.gc_count + 1 && after.used_bytes < before.used_bytes;
}

int main(void)
{
    kmicro_puts("\n=== kmicro self-test: official Kotlin/Native 2.4.21 output on a Cortex-M4 ===\n");
    report("runtime init (module initializers)", runtime_init());
    report("println from Kotlin", hello() == 0);
    report("classes, interface, virtual calls (= 45)", shapes(5) == 45);

    const int32_t rounds = 60;          /* gc_chains sums every node it built: 100-node chains, survivors, array */
    int32_t expect = rounds * 4950 + rounds * (rounds - 1) / 2 + 50 * 49 / 2;
    for (int32_t k = 0; k < rounds; k += 7)
        expect += k * 1000;
    report("garbage collection, 6000+ objects", gc_chains(rounds) == expect);
    report("strings (10 checks, UTF-16, JVM hashCode)", strings(2500) == 0);
    report("exceptions (10 checks, 200+ throws)", exceptions(-3) == 0);
    report("one throw + catch", throw_once(-1) == 1);

    coro_start();                       /* the coroutine suspends at once and waits for events */
    int32_t sum = 0, bad = 0;
    for (int32_t i = 1; i <= 300; i++) {
        sum += i;
        if (coro_event(i) != sum)
            bad++;
    }
    report("coroutine: 300 suspend/resume cycles", bad == 0);
    report("one full GC", full_gc());

    kmicro_stats_t st;
    kmicro_stats(&st);
    stat("\nheap ", st.heap_bytes);
    stat(" B, peak ", st.peak_bytes);
    stat(" B, live peak ", st.live_peak_bytes);
    stat(" B, objects ", st.alloc_count);
    stat(", collections ", st.gc_count);
    stat(", freed ", st.objects_freed);
    kmicro_puts(s_fail == 0 ? "\nresult: ALL PASS\n" : "\nresult: FAILURES\n");
    return s_fail;
}
