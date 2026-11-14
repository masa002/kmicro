/* Atomics of 1, 2 and 4 bytes on a core without LDREX/STREX (ARMv6-M: Cortex-M0, M0+, M1).
 *
 * On the other cores the compiler turns an atomic operation into an exclusive load and store that an interrupt in
 * between makes retry. ARMv6-M has no such instructions, so LLVM calls the __atomic_* functions of this file
 * instead. With one thread, the only other party is an interrupt handler: each function runs with interrupts masked
 * (PRIMASK), a few instructions long, as the 64-bit atomics of atomic64.c do on every core. On a core that has the
 * instructions this file is empty. */
#if defined(__ARM_ARCH) && !(defined(__ARM_FEATURE_LDREX) && (__ARM_FEATURE_LDREX & 4))
#include <stdbool.h>
#include <stdint.h>

static inline uint32_t irq_save(void)
{
    uint32_t pm;
    __asm volatile("mrs %0, primask\n cpsid i" : "=r"(pm) : : "memory");
    return pm;
}

static inline void irq_restore(uint32_t pm) { __asm volatile("msr primask, %0" : : "r"(pm) : "memory"); }

#define KM_ATOMIC_OP(N, T, NAME, EXPR)                                                                         \
    T __atomic_##NAME##_##N(volatile T *p, T v, int order)                                                     \
    {                                                                                                          \
        (void)order;                                                                                           \
        uint32_t pm = irq_save();                                                                              \
        T old = *p;                                                                                            \
        *p = (T)(EXPR);                                                                                        \
        irq_restore(pm);                                                                                       \
        return old;                                                                                            \
    }

#define KM_ATOMICS(N, T)                                                                                       \
    T __atomic_load_##N(const volatile T *p, int order)                                                        \
    {                                                                                                          \
        (void)order;                                                                                           \
        uint32_t pm = irq_save();                                                                              \
        T v = *p;                                                                                              \
        irq_restore(pm);                                                                                       \
        return v;                                                                                              \
    }                                                                                                          \
    void __atomic_store_##N(volatile T *p, T v, int order)                                                     \
    {                                                                                                          \
        (void)order;                                                                                           \
        uint32_t pm = irq_save();                                                                              \
        *p = v;                                                                                                \
        irq_restore(pm);                                                                                       \
    }                                                                                                          \
    bool __atomic_compare_exchange_##N(volatile T *p, T *expected, T desired, bool weak, int success, int failure) \
    {                                                                                                          \
        (void)weak;                                                                                            \
        (void)success;                                                                                         \
        (void)failure;                                                                                         \
        uint32_t pm = irq_save();                                                                              \
        T cur = *p;                                                                                            \
        bool ok = cur == *expected;                                                                            \
        if (ok)                                                                                                \
            *p = desired;                                                                                      \
        else                                                                                                   \
            *expected = cur;                                                                                   \
        irq_restore(pm);                                                                                       \
        return ok;                                                                                             \
    }                                                                                                          \
    KM_ATOMIC_OP(N, T, exchange, v)                                                                            \
    KM_ATOMIC_OP(N, T, fetch_add, old + v)                                                                     \
    KM_ATOMIC_OP(N, T, fetch_sub, old - v)                                                                     \
    KM_ATOMIC_OP(N, T, fetch_and, old & v)                                                                     \
    KM_ATOMIC_OP(N, T, fetch_or, old | v)                                                                      \
    KM_ATOMIC_OP(N, T, fetch_xor, old ^ v)

KM_ATOMICS(1, uint8_t)
KM_ATOMICS(2, uint16_t)
KM_ATOMICS(4, uint32_t)
#else
typedef int km_atomic32_unused;                      /* ISO C: a translation unit is not empty */
#endif
