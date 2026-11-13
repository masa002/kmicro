/* The smallest test: C starts the runtime and calls one Kotlin function (add.kt) by its @CName name. */
#include "kmicro.h"

int32_t k_add(int32_t a, int32_t b);            /* Kotlin: @CName("k_add") fun add(a: Int, b: Int): Int */

int main(void)
{
    kmicro_init();
    int32_t r = k_add(40, 2);
    kmicro_puts("Kotlin add(40, 2) = ");
    kmicro_put_int(r);
    kmicro_puts("\n");
    return r == 42 ? 0 : 1;
}
