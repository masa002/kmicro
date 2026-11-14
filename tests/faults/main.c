/* Faults (faults.kt): run_all builds this file once per test case, with one TEST_* macro defined. */
#include "kmicro.h"

void k_deep(void);
void k_null_field(void);
int32_t k_big_array(void);
int32_t k_parse(int32_t text);

#if defined(TEST_GUARD_SCAN)
extern uint32_t _ebss, _sguard, _eguard;        /* targets/qemu-l475/l475.ld */

/* Calls Kotlin's String.toDouble() with the stack `pad` bytes above the guard. The bytes in between are taken with an
 * alloca that is never written, as the unused part of a large frame is. */
__attribute__((noinline)) static int32_t parse_at(uint32_t pad)
{
    uint32_t sp;
    __asm volatile("mov %0, sp" : "=r"(sp));
    char *p = __builtin_alloca(sp - (uint32_t)&_eguard - pad);
    __asm volatile("" : : "r"(p) : "memory");
    return k_parse(15);
}

/* The last number on QEMU's command line (-semihosting-config arg=N, read with SYS_GET_CMDLINE), or fallback. */
static uint32_t pad_argument(uint32_t fallback)
{
    static char line[80];
    struct { char *buf; uint32_t len; } block = { line, sizeof line };
    register uint32_t r0 __asm("r0") = 0x15u;   /* SYS_GET_CMDLINE */
    register void *r1 __asm("r1") = &block;
    __asm volatile("bkpt 0xAB" : "+r"(r0) : "r"(r1) : "memory");
    if (r0 != 0)
        return fallback;
    uint32_t v = fallback;
    for (const char *p = line; *p; p++)
        if (*p >= '0' && *p <= '9' && (p == line || p[-1] == ' ')) {
            v = 0;
            for (const char *q = p; *q >= '0' && *q <= '9'; q++)
                v = v * 10u + (uint32_t)(*q - '0');
        }
    return v;
}
#endif

int main(void)
{
    kmicro_init();
#if defined(TEST_STACK_OVERFLOW)
    k_deep();
#elif defined(TEST_NULL_FIELD)
    k_null_field();
#elif defined(TEST_GUARD_SCAN)
    /* One call with the stack a given distance above the guard (guard_scan.py runs this image once per distance). It
     * must either return with the unused bytes below the guard untouched, or fault in the guard (the report, exit
     * 99): never write below the guard and go on. */
    uint32_t pad = pad_argument(4096);
    k_parse(15);                                /* first use: globals and tables are created here */
    for (uint32_t *w = &_ebss; (uintptr_t)w < (uintptr_t)&_sguard; w++)
        *w = 0xDEADBEEFu;
    int32_t r = parse_at(pad);
    int changed = 0;
    for (uint32_t *w = &_ebss; (uintptr_t)w < (uintptr_t)&_sguard; w++)
        changed += *w != 0xDEADBEEFu;
    kmicro_puts("stack ");
    kmicro_put_int((int32_t)pad);
    kmicro_puts(" bytes above the guard: toDouble ");
    kmicro_put_int(r);
    kmicro_puts(", words changed below the guard ");
    kmicro_put_int(changed);
    kmicro_puts("\n");
    return changed != 0 || r != 3141;
#elif defined(TEST_BIG_ARRAY)
    kmicro_puts("sum of a 14000-element stack array: ");
    kmicro_put_int(k_big_array());
    kmicro_puts("\n");
    return 0;
#endif
    kmicro_puts("main returned\n");
    return 1;
}
