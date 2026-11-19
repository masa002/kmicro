/* Copyright 2026 the kmicro authors (NOTICE).
 * SPDX-License-Identifier: Apache-2.0 */
/* mps3-an536: an exception that is taken to Hyp mode ends in a fault report of its own. The program runs below Hyp
 * mode and asks for nothing there; an HVC is the one way to get there on purpose. The core enters the vectors of
 * Hyp mode at a 32-byte boundary (HVBAR has no low five bits), so the table must lie on one: at another address
 * the HVC starts in the code in front of the table, or at a wrong entry of it. */
#include "kmicro.h"

void hyp_vectors(void);                 /* targets/qemu-an536/start.c */

int main(void)
{
    volatile uintptr_t table = (uintptr_t)hyp_vectors;
    kmicro_puts("the vectors of Hyp mode are ");
    kmicro_put_int((int32_t)(table % 32u));
    kmicro_puts(" bytes past a 32-byte boundary\n");
    __asm volatile(".arch_extension virt\n hvc #0");
    kmicro_puts("the HVC returned\n");
    return 1;
}
