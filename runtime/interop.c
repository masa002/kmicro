/* cinterop support: thread-state switches (one thread: nothing to do) and the native memory that memScoped,
 * cstr and nativeHeap use (Natives.cpp Kotlin_interop_malloc/free). kmicro has no malloc: a small arena, with
 * first-fit reuse of freed blocks in any order. */
#include <string.h>
#include "kmicro.h"

KM_NOTHROW void Kotlin_mm_switchThreadStateNative(void) {}
KM_NOTHROW void Kotlin_mm_switchThreadStateRunnable(void) {}
KM_NOTHROW void Kotlin_mm_switchThreadStateNative_debug(void) {}
KM_NOTHROW void Kotlin_mm_switchThreadStateRunnable_debug(void) {}

#ifndef KM_INTEROP_BYTES
#define KM_INTEROP_BYTES 1024u
#endif

/* Blocks tile the arena from its start up to s_top: [size | used bit][size of the block below][payload, 8-aligned].
 * Allocation takes the first free block below the top that fits, else bumps the top; while nothing below the top is
 * free (memScoped frees in reverse order) it only bumps. A free merges the block with free neighbours, and a free
 * block that reaches the top lowers it, so no two free blocks are adjacent and the block under the top is in use.
 * A request that does not fit returns NULL, which the stdlib turns into OutOfMemoryError (NativeMem.kt). Interrupts
 * are masked while the block list changes, so a handler may use native memory too. */
static uint8_t s_arena[KM_INTEROP_BYTES] __attribute__((aligned(8)));
static uint32_t s_top;                               /* blocks tile [0, s_top) */
static uint32_t s_last;                              /* size of the block that ends at s_top, 0 when none */
static uint32_t s_holes;                             /* free blocks below s_top */

#define USED 1u
static inline uint32_t *hdr(uint32_t off) { return (uint32_t *)(s_arena + off); }
static inline uint32_t bsize(uint32_t off) { return hdr(off)[0] & ~USED; }
static inline void set_below(uint32_t end, uint32_t size)   /* the block starting at `end` sits on `size` bytes */
{
    if (end < s_top)
        hdr(end)[1] = size;
    else
        s_last = size;
}

static inline uint32_t irq_save(void)
{
#if defined(__thumb__)
    uint32_t pm;
    __asm volatile("mrs %0, primask\n cpsid i" : "=r"(pm) : : "memory");
    return pm;
#else
    return 0;
#endif
}
static inline void irq_restore(uint32_t pm)
{
#if defined(__thumb__)
    __asm volatile("msr primask, %0" : : "r"(pm) : "memory");
#else
    (void)pm;
#endif
}

static uint8_t *take(uint32_t need)                 /* need: header included, a multiple of 8 */
{
    for (uint32_t off = 0; s_holes != 0 && off < s_top; off += bsize(off)) {
        uint32_t size = bsize(off);
        if ((hdr(off)[0] & USED) || size < need)
            continue;
        if (size - need >= 16u) {                    /* split: the rest stays free */
            hdr(off + need)[0] = size - need;
            hdr(off + need)[1] = need;
            set_below(off + size, size - need);
            size = need;
        } else {
            s_holes--;
        }
        hdr(off)[0] = size | USED;
        return s_arena + off;
    }
    if (need > KM_INTEROP_BYTES - s_top)
        return NULL;
    uint8_t *b = s_arena + s_top;
    hdr(s_top)[0] = need | USED;
    hdr(s_top)[1] = s_last;
    s_top += need;
    s_last = need;
    return b;
}

void *Kotlin_interop_malloc(int64_t size, int32_t align)
{
    if (align > 8)
        kmicro_panic("interop malloc: alignment above 8 is not supported");
    if (size < 0 || size > (int64_t)KM_INTEROP_BYTES - 8)   /* before any 32-bit arithmetic */
        return NULL;
    uint32_t need = 8u + (((uint32_t)size + 7u) & ~7u);
    uint32_t pm = irq_save();
    uint8_t *b = take(need);
    irq_restore(pm);
    if (b == NULL)
        return NULL;
    memset(b + 8, 0, need - 8u);                     /* calloc semantics, as the stock runtime */
    return b + 8;
}

void Kotlin_interop_free(void *ptr)
{
    if (ptr == NULL)
        return;
    uint32_t off = (uint32_t)((uint8_t *)ptr - s_arena) - 8u;
    uint32_t pm = irq_save();
    if ((uint8_t *)ptr < s_arena + 8 || off >= s_top || (off & 7u) != 0 || !(hdr(off)[0] & USED))
        kmicro_panic("interop free: not an allocated native block (freed twice?)");
    uint32_t size = bsize(off);
    if (off + size < s_top && !(hdr(off + size)[0] & USED)) {   /* merge the free block above */
        size += bsize(off + size);
        s_holes--;
    }
    uint32_t below = hdr(off)[1];
    if (below != 0 && !(hdr(off - below)[0] & USED)) {        /* merge the free block below */
        off -= below;
        size += below;
        s_holes--;
    }
    if (off + size == s_top) {                       /* it reaches the top: give it back */
        s_top = off;
        s_last = hdr(off)[1];
    } else {
        hdr(off)[0] = size;
        set_below(off + size, size);
        s_holes++;
    }
    irq_restore(pm);
}

/* Scratch memory for the floating-point parser (runtime/dtoa): the same arena, freed before the call returns. */
void *km_dtoa_calloc(uint32_t n, uint32_t size) { return Kotlin_interop_malloc((int64_t)n * size, 8); }
void km_dtoa_free(void *p) { Kotlin_interop_free(p); }

/* Pinning (kotlinx.cinterop pin / usePinned / addressOf). kmicro never moves an object, so the pinned object is the
 * object itself; the Pinned wrapper's reference keeps it alive. DMA buffers in Kotlin rely on this. */
ObjHeader *Kotlin_Interop_pinnable(ObjHeader *obj, ObjHeader **result) { return km_return(result, obj); }

#define KM_ADDRESS_OF(Name, T)                                                                                \
    void *Kotlin_Arrays_get##Name##ArrayAddressOfElement(ObjHeader *a, int32_t i)                             \
    {                                                                                                         \
        if ((uint32_t)i >= ((ArrayHeader *)a)->count_)                                                        \
            ThrowArrayIndexOutOfBoundsException();                                                            \
        return (T *)km_array_data((ArrayHeader *)a) + i;                                                      \
    }
KM_ADDRESS_OF(Byte, int8_t)
KM_ADDRESS_OF(Short, int16_t)
KM_ADDRESS_OF(Char, uint16_t)
KM_ADDRESS_OF(Int, int32_t)
KM_ADDRESS_OF(Long, int64_t)
KM_ADDRESS_OF(Float, float)
KM_ADDRESS_OF(Double, double)
KM_ADDRESS_OF(Boolean, uint8_t)
