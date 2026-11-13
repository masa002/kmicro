/* Classes, an interface and virtual calls (objects.kt). */
#include "kmicro.h"

int32_t k_entry(int32_t n);                     /* Kotlin: @CName("k_entry") fun entry(n: Int): Int */

int main(void)
{
    kmicro_init();
    int32_t r = k_entry(5);                       /* Rect(5,2)=10 + Square(5)=25 + Tri(5,4)=10 */
    kmicro_puts("shapes area sum = ");
    kmicro_put_int(r);
    kmicro_puts(r == 45 ? "  OK\n" : "  WRONG (expected 45)\n");
    return r == 45 ? 0 : 1;
}
