/* The C main of a Kotlin-only program: start the Kotlin runtime, then run the Kotlin `fun main()`.
 *
 *     python tools/kbuild.py build/app app.kt
 *     python tools/qbuild.py build/app/app.elf targets/common/kotlin_main.c build/app/k.o --run
 *
 * kbuild gives the program's main (in any package; `main(args: Array<String>)` gets an empty array) the C name
 * kmicro_kotlin_main. On a board, link this file as the C main the same way. */
#include "kmicro.h"

void kmicro_kotlin_main(void);

/* Used only when the Kotlin code has no main: kbuild found none (kbuild --main makes that a build error). */
__attribute__((weak)) void kmicro_kotlin_main(void)
{
    kmicro_panic("the Kotlin code has no fun main() (build it with kbuild.py --main to check)");
}

int main(void)
{
    kmicro_init();                      /* heap, garbage collector, exceptions */
    kmicro_kotlin_main();
    return 0;
}
