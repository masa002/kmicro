#include "kmicro.h"
void kt_main(void) __asm__("kfun:#main(){}");
int main(void)
{
    kmicro_init();
    kt_main();
    /* The heap after the run, for tools/difftest.py's report (it takes this last line off before comparing). */
    kmicro_stats_t st;
    kmicro_gc();
    kmicro_stats(&st);
    kmicro_puts("kmicro-difftest: heap ");
    kmicro_put_int((int32_t)st.heap_bytes);
    kmicro_puts(" peak ");
    kmicro_put_int((int32_t)st.peak_bytes);
    kmicro_puts(" live ");
    kmicro_put_int((int32_t)st.used_bytes);
    kmicro_puts("\n");
    return 0;
}
