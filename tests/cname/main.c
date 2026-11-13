/* Calls the Kotlin functions of cname.kt by their @CName names, with plain C types. */
#include <stdbool.h>
#include <stdint.h>
#include "kmicro.h"

int32_t k_add(int32_t a, int32_t b);
double k_scale(double x, float f);
bool k_is_even(int64_t n);
uint8_t k_low_byte(uint32_t n);
void k_note(int32_t n);

int main(void)
{
    kmicro_init();
    int32_t r = k_add(40, 2);
    kmicro_puts("add(40, 2) = ");
    kmicro_put_int(r);
    kmicro_puts("\n");
    bool ok = r == 42;
    ok = ok && k_scale(1.5, 4.0f) == 6.0;
    ok = ok && k_is_even(10000000000LL) && !k_is_even(-3);
    ok = ok && k_low_byte(0x12345678u) == 0x78u;
    k_note(7);
    kmicro_puts(ok ? "cname: OK\n" : "cname: WRONG\n");
    return ok ? 0 : 1;
}
