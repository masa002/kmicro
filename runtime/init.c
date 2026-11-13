/* Runtime start: module initializer list, thread-local records (= ordinary storage: one thread), safepoints. */
#include "kmicro.h"

static InitNode *s_head, *s_tail;
static int s_initialized;

KM_NOTHROW void AppendToInitializersTail(InitNode *node)
{
    if (s_head == NULL)
        s_head = node;
    else
        s_tail->next = node;
    s_tail = node;
}

/* ---- TLS (Memory.h AddTLSRecord / CommitTLSStorage / LookupTLS): a key per module, `size` object slots ---- */
#ifndef KM_TLS_KEYS
#define KM_TLS_KEYS  8                               /* modules with thread-local globals (-D KM_TLS_KEYS=...) */
#endif
#ifndef KM_TLS_SLOTS
#define KM_TLS_SLOTS 64                              /* @ThreadLocal reference slots, all modules together */
#endif
static struct { void **key; int offset, size; } s_tls[KM_TLS_KEYS];
static int s_tls_n, s_tls_used;
ObjHeader *kmicro_tls_slots[KM_TLS_SLOTS];          /* GC roots */
int kmicro_tls_slot_count;

KM_NOTHROW void AddTLSRecord(MemoryState *memory, void **key, int size)
{
    (void)memory;
    for (int i = 0; i < s_tls_n; i++)
        if (s_tls[i].key == key) {
            if (s_tls[i].size != size)
                kmicro_panic("TLS record size mismatch");
            return;
        }
    if (s_tls_n == KM_TLS_KEYS)
        kmicro_panic("TLS table full (raise KM_TLS_KEYS, now " KM_STR(KM_TLS_KEYS) ")");
    if (s_tls_used + size > KM_TLS_SLOTS)
        kmicro_panic("TLS table full (raise KM_TLS_SLOTS, now " KM_STR(KM_TLS_SLOTS) ")");
    s_tls[s_tls_n].key = key;
    s_tls[s_tls_n].offset = s_tls_used;
    s_tls[s_tls_n].size = size;
    s_tls_n++;
    s_tls_used += size;
}

KM_NOTHROW ObjHeader **LookupTLS(void **key, int index)
{
    for (int i = 0; i < s_tls_n; i++)
        if (s_tls[i].key == key) {
            if (index >= s_tls[i].size)
                kmicro_panic("TLS index out of range");
            return &kmicro_tls_slots[s_tls[i].offset + index];
        }
    kmicro_panic("unknown TLS key");
}

/* ---- safepoints: one thread, nothing to stop for. Empty, so full LTO removes the calls. ---- */
KM_NOTHROW void Kotlin_mm_safePointFunctionPrologue(void) {}
KM_NOTHROW void Kotlin_mm_safePointWhileLoopBody(void) {}

static void run_initializers(int mode)
{
    for (InitNode *n = s_head; n != NULL; n = n->next)
        n->init(mode, NULL);
}

void kmicro_init(void)
{
    if (s_initialized)
        return;
    s_initialized = 1;
    run_initializers(KM_ALLOC_THREAD_LOCAL_GLOBALS);
    kmicro_tls_slot_count = s_tls_used;              /* CommitTLSStorage: the static slots are already zero */
    run_initializers(KM_INIT_GLOBALS);
    run_initializers(KM_INIT_THREAD_LOCAL_GLOBALS);
}

KM_NOTHROW void Kotlin_initRuntimeIfNeeded(void) { kmicro_init(); }

void kmicro_put_int(int32_t v)
{
    char b[12], *p = b + sizeof b - 1;
    uint32_t u = v < 0 ? 0u - (uint32_t)v : (uint32_t)v;
    *p = 0;
    do {
        *--p = (char)('0' + u % 10u);
        u /= 10u;
    } while (u);
    if (v < 0)
        *--p = '-';
    kmicro_puts(p);
}

/* "... at 0x0800abcd": tools/symbolize.py turns the address into the function that made the faulting call. */
__attribute__((noreturn)) void kmicro_panic(const char *what)
{
    kmicro_puts("kmicro panic: ");
    kmicro_puts(what);
    if (km_fault_pc != NULL) {
        char b[] = " at 0x00000000";
        uint32_t v = (uint32_t)km_fault_pc & ~1u;    /* without the Thumb bit, as in stack traces */
        for (int i = 0; i < 8; i++)
            b[13 - i] = "0123456789abcdef"[(v >> (4 * i)) & 15u];
        kmicro_puts(b);
    }
    kmicro_puts("\n");
    extern void kmicro_exit(int);
    kmicro_exit(98);
    for (;;) {
    }
}
