/* The runtime natives (natives.kt): run_all builds this file once per test case, with one TEST_* macro defined. It
 * provides the board hooks a case needs: console input (kmicro_getc) and, for one case, an entropy source. */
#include "kmicro.h"

void k_platform(void);
void k_input(void);
void k_canon_eq(void);
void k_weak_reference(void);
void k_worker(void);
void k_gc_tuning(void);
void k_uuid(void);

#if defined(TEST_INPUT)                 /* CRLF and LF line ends, UTF-8, an empty line, a last line without '\n' */
static const char s_input[] = "hello\r\nw\xc3\xb6rld\n\nlast";
#else
static const char s_input[] = "";
#endif
static unsigned s_pos;

int kmicro_getc(void)
{
    return s_pos < sizeof s_input - 1 ? (unsigned char)s_input[s_pos++] : -1;
}

#if defined(TEST_UUID_ENTROPY)
/* Not random: a fixed pattern, so that the output can be compared. A board fills buf from its RNG. */
void kmicro_random_bytes(void *buf, size_t n)
{
    for (size_t i = 0; i < n; i++)
        ((unsigned char *)buf)[i] = (unsigned char)(i * 29 + 7);
}
#endif

int main(void)
{
    kmicro_init();
#if defined(TEST_PLATFORM)
    k_platform();
#elif defined(TEST_INPUT)
    k_input();
#elif defined(TEST_CANON_EQ)
    k_canon_eq();
#elif defined(TEST_WEAK_REFERENCE)
    k_weak_reference();
#elif defined(TEST_WORKER)
    k_worker();
#elif defined(TEST_GC_TUNING)
    k_gc_tuning();
#elif defined(TEST_UUID) || defined(TEST_UUID_ENTROPY)
    k_uuid();
#endif
    kmicro_puts("main returned\n");
    return 0;
}
