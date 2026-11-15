/* Copyright 2026 the kmicro authors (NOTICE).
 * SPDX-License-Identifier: Apache-2.0 */
/* A C++ file includes kmicro.h and hw.h: the functions keep their C names there, so the calls link. */
#include "kmicro.h"
#include "hw.h"

static uint32_t s_word;

struct Doubler {
    int32_t twice(int32_t v) const { return 2 * v; }
};

int main()
{
    kmicro_init();
    hw_wr32((uint32_t)&s_word, 617u);
    kmicro_puts("from C++: ");
    kmicro_put_int(Doubler().twice((int32_t)hw_rd32((uint32_t)&s_word)));
    kmicro_puts("\n");
    return 0;
}
