/* Copyright 2026 the kmicro authors (NOTICE).
 * SPDX-License-Identifier: Apache-2.0 */
/* The smallest kmicro program: C starts the Kotlin runtime and calls one Kotlin function by a plain C name. */
#include "kmicro.h"
#include "hello.h"

int main(void)
{
    kmicro_init();                      /* heap, garbage collector, exceptions */
    return hello(3) == 3 ? 0 : 1;       /* the exit code QEMU reports */
}
