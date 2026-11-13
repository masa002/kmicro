/* Exceptions: throw, catch, finally and Result (exceptions.kt), then an uncaught one, which stops the program with
 * the uncaught-exception report and exit 98. */
#include "kmicro.h"

int32_t k_exc(int32_t n);                       /* Kotlin: @CName("k_exc") fun exc(n: Int): Int */
int32_t k_uncaught(int32_t n);                  /* Kotlin: @CName("k_uncaught") fun uncaught(n: Int): Int */

int main(void)
{
    kmicro_init();
    int32_t f = k_exc(-3);
    kmicro_stats_t st;
    kmicro_stats(&st);
    kmicro_puts("exception checks failed mask = ");
    kmicro_put_int(f);
    kmicro_puts(f == 0 ? "  OK" : "  WRONG");
    kmicro_puts("   (gcs="); kmicro_put_int((int32_t)st.gc_count); kmicro_puts(")\n");
    if (f != 0)
        return 1;
    kmicro_puts("now an uncaught one (expected to stop with a report):\n");
    k_uncaught(-5);
    return 2;
}
