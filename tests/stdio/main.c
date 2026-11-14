/* newlib's stdio from C and from Kotlin (stdio.kt): what printf, puts and fprintf(stderr) write goes where println
 * goes, through the runtime's _write. */
#include <stdio.h>
#include "kmicro.h"

void k_printf(void);

int main(void)
{
    kmicro_init();
    int n = printf("printf from C says %d\n", 42);
    printf("printf returned %d\n", n);
    k_printf();
    puts("puts from C");
    fprintf(stderr, "stderr from C\n");
    printf("no line end yet, ");                     /* stdout is line buffered: this waits for the next line end */
    kmicro_puts("[kmicro_puts]");
    printf("now\n");
    printf("%s|%s|%s\n", "a line longer than the 64 bytes that one kmicro_puts takes from the default kmicro_write",
           "0123456789", "end");
    return 0;
}
