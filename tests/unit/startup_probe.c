/* C programs for test_startup.py, one per PROBE value, run on the QEMU l475 target. */
#include "kmicro.h"

extern uint32_t _sbss, _ebss;

__attribute__((noinline)) uint32_t probe_bad_read(void) { return *(volatile uint32_t *)0x70000000u; }

const uint32_t *volatile probe_null;
__attribute__((noinline)) uint32_t probe_null_read(void) { return probe_null[3]; }

__attribute__((noinline)) void probe_undefined(void) { __asm volatile("udf #0"); }

static uint32_t bss_sum(void)
{
    uint32_t s = 0;
    for (volatile uint32_t *p = &_sbss; p < &_ebss; p++)
        s = s * 31u + *p;
    return s;
}

/* Recursion that checks at every level that the stack has not written .bss (the Kotlin heap lives there). */
__attribute__((noinline)) uint32_t probe_deep(uint32_t n, uint32_t ref)
{
    volatile uint32_t pad[8];
    pad[0] = n;
    if (bss_sum() != ref) {
        kmicro_puts("bss changed at depth ");
        kmicro_put_int((int32_t)n);
        kmicro_puts("\n");
        return 1;
    }
    return probe_deep(n + 1, ref) + pad[0];
}

int main(void)
{
    kmicro_init();
    kmicro_puts("probe start\n");
#if PROBE == 1
    return (int)probe_bad_read();
#elif PROBE == 2
    probe_undefined();
    return 0;
#elif PROBE == 3
    return (int)probe_deep(0, bss_sum());
#elif PROBE == 4
    return (int)probe_null_read();
#endif
}
