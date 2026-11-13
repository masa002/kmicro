/* 64-bit atomics for ARMv7-M (no LDREXD/STREXD): the libatomic ABI that LLVM calls for i64 atomicrmw/cmpxchg
 * (AtomicLong, kotlin.random). libgcc for v7e-m has none. One core and interrupt handlers never touch Kotlin
 * data, so masking interrupts around the access is enough; PRIMASK is saved and restored, never just enabled. */
#include <stdbool.h>
#include <stdint.h>

static inline uint32_t irq_save(void)
{
    uint32_t pm;
    __asm volatile("mrs %0, primask\n cpsid i" : "=r"(pm) : : "memory");
    return pm;
}
static inline void irq_restore(uint32_t pm) { __asm volatile("msr primask, %0" : : "r"(pm) : "memory"); }

uint64_t __atomic_load_8(const volatile void *p, int order)
{
    (void)order;
    uint32_t pm = irq_save();
    uint64_t v = *(const volatile uint64_t *)p;
    irq_restore(pm);
    return v;
}

void __atomic_store_8(volatile void *p, uint64_t v, int order)
{
    (void)order;
    uint32_t pm = irq_save();
    *(volatile uint64_t *)p = v;
    irq_restore(pm);
}

uint64_t __atomic_exchange_8(volatile void *p, uint64_t v, int order)
{
    (void)order;
    uint32_t pm = irq_save();
    uint64_t old = *(volatile uint64_t *)p;
    *(volatile uint64_t *)p = v;
    irq_restore(pm);
    return old;
}

bool __atomic_compare_exchange_8(volatile void *p, void *expected, uint64_t desired, bool weak, int success,
                                 int failure)
{
    (void)weak;
    (void)success;
    (void)failure;
    uint32_t pm = irq_save();
    uint64_t cur = *(volatile uint64_t *)p;
    bool ok = cur == *(uint64_t *)expected;
    if (ok)
        *(volatile uint64_t *)p = desired;
    else
        *(uint64_t *)expected = cur;
    irq_restore(pm);
    return ok;
}

#define KM_FETCH_OP(name, op)                                                                                  \
    uint64_t __atomic_fetch_##name##_8(volatile void *p, uint64_t v, int order)                                \
    {                                                                                                          \
        (void)order;                                                                                           \
        uint32_t pm = irq_save();                                                                              \
        uint64_t old = *(volatile uint64_t *)p;                                                                \
        *(volatile uint64_t *)p = old op v;                                                                    \
        irq_restore(pm);                                                                                       \
        return old;                                                                                            \
    }
KM_FETCH_OP(add, +)
KM_FETCH_OP(sub, -)
KM_FETCH_OP(and, &)
KM_FETCH_OP(or, |)
KM_FETCH_OP(xor, ^)
