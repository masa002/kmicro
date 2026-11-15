/* Copyright 2026 the kmicro authors (NOTICE).
 * SPDX-License-Identifier: Apache-2.0 */
/* A core of ARMv6-M or ARMv8-M Baseline faults on an unaligned LDR or STR. QEMU runs the code of those cores on a
 * larger core, which allows them, so the start code asks that core to fault too (CCR.UNALIGN_TRP). This test checks
 * that setting for such a core, and for the other cores that an unaligned read gives the bytes. */
#include "kmicro.h"

#ifdef __ARM_FEATURE_UNALIGNED
static uint8_t s_bytes[8] = {1, 2, 3, 4, 5, 6, 7, 8};
#endif

int main(void)
{
#ifdef __ARM_FEATURE_UNALIGNED
    volatile uintptr_t odd = (uintptr_t)s_bytes + 1;
    int ok = *(volatile uint32_t *)odd == 0x05040302u;
#else
    int ok = (*(volatile uint32_t *)0xE000ED14 >> 3) & 1;      /* CCR.UNALIGN_TRP */
#endif
    kmicro_puts("unaligned access behaves as on this core  ");
    kmicro_puts(ok ? "OK\n" : "FAILED\n");
    return ok ? 0 : 1;
}
