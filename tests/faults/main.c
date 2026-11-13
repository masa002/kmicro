/* Faults (faults.kt): run_all builds this file once per test case, with one TEST_* macro defined. */
#include "kmicro.h"

void k_deep(void);
void k_null_field(void);
int32_t k_big_array(void);

int main(void)
{
    kmicro_init();
#if defined(TEST_STACK_OVERFLOW)
    k_deep();
#elif defined(TEST_NULL_FIELD)
    k_null_field();
#elif defined(TEST_BIG_ARRAY)
    kmicro_puts("sum of a 14000-element stack array: ");
    kmicro_put_int(k_big_array());
    kmicro_puts("\n");
    return 0;
#endif
    kmicro_puts("main returned\n");
    return 1;
}
