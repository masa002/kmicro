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
#endif
    kmicro_puts("main returned\n");
    return 0;
}
