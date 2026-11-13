/* The native-memory arena (nativeHeap, memScoped): freeing a block twice must stop the program, also when the first
 * free merged it into the free block below it. C only: these are the functions Kotlin code calls. */
#include "kmicro.h"
void *Kotlin_interop_malloc(int64_t size, int32_t align);
void Kotlin_interop_free(void *ptr);

int main(void)
{
    kmicro_init();
    void *a = Kotlin_interop_malloc(8, 8), *b = Kotlin_interop_malloc(8, 8), *c = Kotlin_interop_malloc(8, 8);
    (void)c;
    Kotlin_interop_free(a);
    Kotlin_interop_free(b);          /* merges with a's free block below */
    kmicro_puts("second free of b\n");
    Kotlin_interop_free(b);
    kmicro_puts("no panic\n");
    return 1;
}
