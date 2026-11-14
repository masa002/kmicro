/* A handler that uses a file's globals while the thread code is creating them (window.kt): the runtime must stop the
 * program, because the globals are still unset and a handler cannot wait for the thread code. */
#include "kmicro.h"

/* run_all builds this file once for ordinary globals (window.kt) and once, with TEST_THREAD_LOCAL defined, for
 * @ThreadLocal globals (window_tls.kt). */
#if defined(TEST_THREAD_LOCAL)
#define w_thread_use w_thread_use_local
#define w_handler_use w_handler_use_local
#endif
int32_t w_thread_use(void);             /* Kotlin: the first use; its initializer pends SysTick */
int32_t w_handler_use(void);            /* Kotlin: reads a global of the same file */

static volatile int32_t s_seen = -1;

void SysTick_Handler(void)
{
    s_seen = w_handler_use();
}

int main(void)
{
    kmicro_init();
    int32_t limit = w_thread_use();
    kmicro_puts("the handler returned: it read limit = ");
    kmicro_put_int(s_seen);
    kmicro_puts(", the thread code ");
    kmicro_put_int(limit);
    kmicro_puts("\n");
    return 1;
}
