/* cinterop support: thread-state switches (one thread: nothing to do) and the native memory that memScoped,
 * cstr and nativeHeap use (Natives.cpp Kotlin_interop_malloc/free). kmicro has no malloc: a small arena,
 * last-in-first-out like memScoped, with a free list fallback for out-of-order frees. */
#include <string.h>
#include "kmicro.h"

KM_NOTHROW void Kotlin_mm_switchThreadStateNative(void) {}
KM_NOTHROW void Kotlin_mm_switchThreadStateRunnable(void) {}
KM_NOTHROW void Kotlin_mm_switchThreadStateNative_debug(void) {}
KM_NOTHROW void Kotlin_mm_switchThreadStateRunnable_debug(void) {}

#ifndef KM_INTEROP_BYTES
#define KM_INTEROP_BYTES 1024u
#endif

/* Block: [size | used bit][payload, 8-aligned]. Allocation bumps the top; a free of the top block lowers the top
 * (and any freed blocks right under it), a free elsewhere only marks the block. */
static uint8_t s_arena[KM_INTEROP_BYTES] __attribute__((aligned(8)));
static uint32_t s_top;                               /* bytes in use from the start */

void *Kotlin_interop_malloc(int64_t size, int32_t align)
{
    if (size < 0 || align > 8)
        kmicro_panic("interop malloc: unsupported size or alignment");
    uint32_t need = 8u + (((uint32_t)size + 7u) & ~7u);
    if (s_top + need > KM_INTEROP_BYTES)
        kmicro_panic("interop arena full (raise KM_INTEROP_BYTES)");
    uint32_t *hdr = (uint32_t *)(s_arena + s_top);
    hdr[0] = need | 1u;                              /* size, used */
    hdr[1] = s_top;                                  /* where the block starts (to walk back) */
    s_top += need;
    void *p = hdr + 2;
    memset(p, 0, need - 8u);                         /* calloc semantics, as the stock runtime */
    return p;
}

void Kotlin_interop_free(void *ptr)
{
    if (ptr == NULL)
        return;
    uint32_t *hdr = (uint32_t *)ptr - 2;
    hdr[0] &= ~1u;
    for (;;) {                                       /* pop every free block at the top */
        if (s_top == 0)
            return;
        uint32_t *last = NULL;
        for (uint32_t off = 0; off < s_top;) {      /* find the top block (arena is tiny) */
            uint32_t *h = (uint32_t *)(s_arena + off);
            last = h;
            off += h[0] & ~1u;
        }
        if (last == NULL || (last[0] & 1u))
            return;
        s_top = last[1];
    }
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
