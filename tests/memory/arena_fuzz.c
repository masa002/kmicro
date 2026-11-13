/* Random malloc/free on the native-memory arena (nativeHeap, memScoped), through the functions Kotlin code calls:
 * every live block keeps its fill pattern, blocks never overlap, a request fails only when no free run is big enough,
 * and everything freed gives back the whole arena. C only. */
#include "kmicro.h"
void *Kotlin_interop_malloc(int64_t size, int32_t align);
void Kotlin_interop_free(void *ptr);

#define N 24
static uint8_t *s_p[N];
static uint32_t s_n[N];
static uint32_t s_rng = 12345;
static uint32_t rnd(void) { s_rng = s_rng * 1103515245u + 12345u; return s_rng >> 8; }

static int check(void)
{
    for (int i = 0; i < N; i++) {
        if (!s_p[i]) continue;
        for (uint32_t k = 0; k < s_n[i]; k++)
            if (s_p[i][k] != (uint8_t)(i * 7 + 1)) return 1;
        for (int j = 0; j < N; j++)
            if (j != i && s_p[j] && s_p[i] < s_p[j] + s_n[j] + 8 && s_p[j] < s_p[i] + s_n[i] + 8) return 2;
    }
    return 0;
}

static uint8_t *s_lo;                                    /* arena start (the first block's header) */

/* The largest free run between live blocks (headers included); the arena is 1024 bytes. */
static uint32_t largest_gap(void)
{
    uint8_t *at = s_lo;
    uint32_t best = 0;
    for (;;) {
        uint8_t *next = s_lo + 1024;
        int ni = -1;
        for (int j = 0; j < N; j++)
            if (s_p[j] && s_p[j] - 8 >= at && s_p[j] - 8 < next) { next = s_p[j] - 8; ni = j; }
        if ((uint32_t)(next - at) > best) best = (uint32_t)(next - at);
        if (ni < 0) return best;
        at = s_p[ni] - 8 + (*(uint32_t *)(s_p[ni] - 8) & ~1u);   /* the block size in its header */
    }
}

int main(void)
{
    kmicro_init();
    s_lo = (uint8_t *)Kotlin_interop_malloc(1, 1) - 8;
    Kotlin_interop_free(s_lo + 8);
    int fails = 0, ok = 0, bad = 0;
    for (int round = 0; round < 200000 && !bad; round++) {
        int i = (int)(rnd() % N);
        if (s_p[i]) {
            Kotlin_interop_free(s_p[i]);
            s_p[i] = 0;
        } else {
            uint32_t n = rnd() % 200u;
            uint8_t *p = Kotlin_interop_malloc(n, (int32_t)(1u << (rnd() % 4u)));
            if (p == 0) {
                fails++;
                if (largest_gap() >= 8u + ((n + 7u) & ~7u)) bad = 20;   /* refused although a free run fits */
                continue;
            }
            for (uint32_t k = 0; k < n; k++)
                if (p[k] != 0) bad = 10;        /* calloc semantics */
            for (uint32_t k = 0; k < n; k++)
                p[k] = (uint8_t)(i * 7 + 1);
            s_p[i] = p;
            s_n[i] = n;
            ok++;
        }
        if (!bad) bad = check();
    }
    for (int i = 0; i < N; i++)
        if (s_p[i]) { Kotlin_interop_free(s_p[i]); s_p[i] = 0; }
    uint8_t *all = Kotlin_interop_malloc(1024 - 8, 8);   /* the whole arena is back in one piece */
    void *too_big = Kotlin_interop_malloc(1024 - 7, 1);
    void *huge = Kotlin_interop_malloc(0x7FFFFFFFFFFFFFF9LL, 1);
    void *neg = Kotlin_interop_malloc(-1, 1);
    kmicro_puts("allocs "); kmicro_put_int(ok);
    kmicro_puts(", refused "); kmicro_put_int(fails);
    kmicro_puts(", bad "); kmicro_put_int(bad);
    kmicro_puts(", whole arena after freeing all: "); kmicro_puts(all ? "yes" : "NO");
    kmicro_puts(", oversize NULL: "); kmicro_puts(!too_big && !huge && !neg ? "yes" : "NO");
    kmicro_puts("\n");
    Kotlin_interop_free(all);
    return bad != 0 || all == 0 || too_big || huge || neg;
}
