/* A Kotlin interrupt handler: C starts the runtime and the Kotlin globals, Kotlin does the rest (irq.kt). */
#include "kmicro.h"
#include "irq.h"

int main(void)
{
    kmicro_init();                      /* heap, garbage collector, exceptions */
    kt_init_all();                      /* the Kotlin globals, before the first interrupt can use them */
    return run_ticks(5) == 5 ? 0 : 1;   /* the exit code QEMU reports */
}
