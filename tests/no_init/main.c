/* Copyright 2026 the kmicro authors (NOTICE).
 * SPDX-License-Identifier: Apache-2.0 */
/* A C main that forgets kmicro_init() (local.kt): the runtime must name the missing call. */
#include "kmicro.h"

void kmicro_kotlin_main(void);

int main(void)
{
    kmicro_kotlin_main();
    return 1;
}
