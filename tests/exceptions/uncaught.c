/* Uncaught exceptions and the unhandled-exception hook (uncaught.kt): run_all builds this file once per test case,
 * with one TEST_* macro defined, and the case's Kotlin function runs. */
#include "kmicro.h"

void k_cause_chain(void);
void k_long_message(void);
void k_failed_initializer(void);
void k_hook(void);
void k_hook_terminates(void);
void k_hook_throws(void);
void k_process_without_hook(void);
void k_process_with_hook(void);
void k_circular_cause(void);
void k_message_throws(void);
void k_local_class(void);
void k_anonymous_object(void);

#if defined(TEST_BL_ENTRY)
/* A naked function that calls with bl, as a reset entry that reaches the C start function with bl: from then on lr
 * points into the function, whose unwind entry says "return through lr", so unwinding its frame gives the same frame
 * again. The search for a handler must end there. k_cause_chain throws out of a recursive call, the other way the
 * unwinder looks one return address up twice in a row. */
__attribute__((used)) void below_bl(void) { k_cause_chain(); }

__attribute__((naked, noinline)) static void bl_entry(void)
{
    __asm volatile("bl below_bl\n"
                   "b .\n");
}
#endif

int main(void)
{
    kmicro_init();
#if defined(TEST_CAUSE_CHAIN)
    k_cause_chain();
#elif defined(TEST_LONG_MESSAGE)
    k_long_message();
#elif defined(TEST_FAILED_INITIALIZER)
    k_failed_initializer();
#elif defined(TEST_HOOK)
    k_hook();
#elif defined(TEST_HOOK_TERMINATES)
    k_hook_terminates();
#elif defined(TEST_HOOK_THROWS)
    k_hook_throws();
#elif defined(TEST_PROCESS_WITHOUT_HOOK)
    k_process_without_hook();
#elif defined(TEST_PROCESS_WITH_HOOK)
    k_process_with_hook();
#elif defined(TEST_CIRCULAR_CAUSE)
    k_circular_cause();
#elif defined(TEST_MESSAGE_THROWS)
    k_message_throws();
#elif defined(TEST_LOCAL_CLASS)
    k_local_class();
#elif defined(TEST_ANONYMOUS_OBJECT)
    k_anonymous_object();
#elif defined(TEST_BL_ENTRY)
    bl_entry();
#endif
    kmicro_puts("main returned\n");
    return 0;
}
