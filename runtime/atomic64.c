/* Copyright 2026 the kmicro authors (NOTICE).
 * SPDX-License-Identifier: Apache-2.0 */
/* 64-bit atomics for the M profile (no LDREXD/STREXD): the libatomic ABI that LLVM calls for i64 atomicrmw/cmpxchg
 * (AtomicLong, kotlin.random). libgcc for v7e-m has none. There is one core, so masking interrupts around the
 * access makes it atomic against interrupt handlers as well, which may use the same atomics (km_cpu.h).
 * The A and R profiles have the two instructions and the compiler uses them, so there this file is empty: a function
 * of this file that only masks interrupts would not make an exclusive store of the interrupted code fail.
 * The condition is the profile, not __ARM_FEATURE_LDREX: clang gives that macro the bit for 64 bits on ARMv8-M too,
 * where it still calls these functions. An ARM core from before the profiles is asked for that bit: ARMv6K
 * (ARM1176JZF-S) has the two instructions, and the cores before it (ARM926EJ-S, ARM7TDMI) get these functions. */
#if !defined(__arm__) || (defined(__ARM_ARCH_PROFILE) ? __ARM_ARCH_PROFILE == 'M' : !(__ARM_FEATURE_LDREX & 8))
#include <stdbool.h>
#include <stdint.h>
#include "km_cpu.h"

uint64_t __atomic_load_8(const volatile void *p, int order)
{
    (void)order;
    uint32_t pm = km_irq_save();
    uint64_t v = *(const volatile uint64_t *)p;
    km_irq_restore(pm);
    return v;
}

void __atomic_store_8(volatile void *p, uint64_t v, int order)
{
    (void)order;
    uint32_t pm = km_irq_save();
    *(volatile uint64_t *)p = v;
    km_irq_restore(pm);
}

uint64_t __atomic_exchange_8(volatile void *p, uint64_t v, int order)
{
    (void)order;
    uint32_t pm = km_irq_save();
    uint64_t old = *(volatile uint64_t *)p;
    *(volatile uint64_t *)p = v;
    km_irq_restore(pm);
    return old;
}

bool __atomic_compare_exchange_8(volatile void *p, void *expected, uint64_t desired, int success, int failure)
{
    (void)success;
    (void)failure;
    uint32_t pm = km_irq_save();
    uint64_t cur = *(volatile uint64_t *)p;
    bool ok = cur == *(uint64_t *)expected;
    if (ok)
        *(volatile uint64_t *)p = desired;
    else
        *(uint64_t *)expected = cur;
    km_irq_restore(pm);
    return ok;
}

#define KM_FETCH_OP(name, op)                                                                                  \
    uint64_t __atomic_fetch_##name##_8(volatile void *p, uint64_t v, int order)                                \
    {                                                                                                          \
        (void)order;                                                                                           \
        uint32_t pm = km_irq_save();                                                                              \
        uint64_t old = *(volatile uint64_t *)p;                                                                \
        *(volatile uint64_t *)p = old op v;                                                                    \
        km_irq_restore(pm);                                                                                       \
        return old;                                                                                            \
    }
KM_FETCH_OP(add, +)
KM_FETCH_OP(sub, -)
KM_FETCH_OP(and, &)
KM_FETCH_OP(or, |)
KM_FETCH_OP(xor, ^)
#else
typedef int km_atomic64_unused;                      /* ISO C: a translation unit is not empty */
#endif
