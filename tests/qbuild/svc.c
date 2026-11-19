/* Copyright 2026 the kmicro authors (NOTICE).
 * SPDX-License-Identifier: Apache-2.0 */
/* An SVC that is not the semihosting call ends in the fault report of the start code. A Cortex-A or Cortex-R core
 * takes it in Supervisor mode, the mode the program runs in, so the report cannot read the program's stack pointer
 * and lr in another mode, as it does for the other faults: the stack pointer it prints must still be the program's
 * (the expected output has its first digits), and it must not print the exception's return address as the lr. */
#include "kmicro.h"

int main(void)
{
    __asm volatile("svc 1");
    kmicro_puts("the SVC returned\n");
    return 1;
}
