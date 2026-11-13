/* Memory limits (memory.kt, globals.kt): run_all builds this file once per test case, with one TEST_* macro defined. */
#include "kmicro.h"

int32_t k_too_big(void);
int32_t k_heap_full(void);
void k_native_oom(void);
void k_stable_refs(void);
int32_t k_uppercase(void);
int32_t k_is_letter(void);
int32_t k_category(void);
void k_println(void);
int32_t k_globals_sum(void);

/* The heap kept by one Kotlin call: live bytes after a full collection, after the call minus before. */
static void kept(const char *what, int32_t (*call)(void))
{
    kmicro_stats_t a, b;
    kmicro_gc();
    kmicro_stats(&a);
    call();
    kmicro_gc();
    kmicro_stats(&b);
    kmicro_puts(what);
    kmicro_put_int((int32_t)(b.used_bytes - a.used_bytes));
    kmicro_puts(" B kept\n");
}

int main(void)
{
    kmicro_init();
#if defined(TEST_TOO_BIG)
    return k_too_big() == -1 ? 0 : 1;
#elif defined(TEST_HEAP_FULL)
    k_heap_full();
#elif defined(TEST_NATIVE_OOM)
    k_native_oom();
    return 0;
#elif defined(TEST_STABLE_REFS)
    k_stable_refs();
#elif defined(TEST_UNICODE_TABLES)
    k_println();                        /* the first println creates what printing needs, before the measurements */
    kept("\"abc\".uppercase(): ", k_uppercase);
    kept("'\\u00e9'.isLetter(): ", k_is_letter);
    kept("'\\u00e9'.category: ", k_category);
    return 0;
#elif defined(TEST_GLOBALS)
    int32_t sum = k_globals_sum();
    kmicro_puts("sum of 200 globals: ");
    kmicro_put_int(sum);
    kmicro_puts("\n");
    return 0;
#endif
    kmicro_puts("main returned\n");
    return 1;
}
