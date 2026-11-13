#include "kmicro.h"
int32_t k_str(int32_t n) __asm__("kfun:#str(kotlin.Int){}kotlin.Int");
int main(void)
{
    kmicro_init();
    int32_t f = k_str(2500);
    kmicro_puts("string checks failed mask = ");
    kmicro_put_int(f);
    kmicro_puts(f == 0 ? "  OK\n" : "  WRONG\n");
    return f;
}
