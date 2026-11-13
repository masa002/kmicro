/* Calls the cinterop test's Kotlin function from an archive of its objects (kotlin.a: k.o and bridges.o) without the
 * C side of tests/cinterop: the link must fail on the C functions Kotlin calls, naming the archive. */
#include "kmicro.h"

int32_t k_poke(int32_t n);

int main(void)
{
    kmicro_init();
    return k_poke(7) == 1003 ? 0 : 1;
}
