/* Copyright 2026 the kmicro authors (NOTICE).
 * SPDX-License-Identifier: Apache-2.0 */
/* The C side of the cinterop_shapes test: implements drv.h and checks every call shape of shapes.kt, calling the
 * Kotlin functions by their @CName names. Built with TEST_CALLBACK_THROWS, it runs a callback that throws instead. */
#include "kmicro.h"
#include <stdarg.h>
#include <stdlib.h>
#include "drv.h"

int32_t drv_counter = 10;
pt_t pt_make(int32_t x, int32_t y) { pt_t p = { x, y }; return p; }
int32_t pt_sum(pt_t p) { return p.x + p.y; }
vec2_t vec_scale(vec2_t v, float k) { vec2_t r = { v.x * k, v.y * k }; return r; }
cplx_t cplx_conj(cplx_t z) { cplx_t r = { z.re, -z.im }; return r; }
int32_t vec_apply(vec_cb_t cb)
{
    vec2_t v = { 1.5f, -2.5f };
    vec2_t r = cb(v, 2.0f);
    return (int32_t)(r.x * 100.0f + r.y);
}

static drv_cb_t s_cb;
void drv_set_cb(drv_cb_t cb) { s_cb = cb; }
int32_t drv_fire(int32_t v) { return s_cb ? s_cb(v) : -1; }
void drv_sort(int32_t *v, int32_t n, int (*cmp)(const void *, const void *))
{
    qsort(v, (size_t)n, sizeof *v, cmp);
}

int32_t sum_va(int32_t n, ...)
{
    va_list a;
    va_start(a, n);
    int32_t s = 0;
    for (int32_t i = 0; i < n; i++)
        s += va_arg(a, int32_t);
    va_end(a);
    return s;
}

uint32_t plain_fn(uint32_t v) { return v; }

int32_t kt_global(void);
int32_t kt_struct_return(void);
int32_t kt_struct_arg(void);
int32_t kt_float_struct_return(void);
int32_t kt_double_struct_return(void);
int32_t kt_float_struct_callback(void);
int32_t kt_callback(void);
int32_t kt_sort_descending(void);
int32_t kt_varargs(void);
int32_t kt_inline_loop(void);
int32_t kt_inline_asm(void);
int32_t kt_inline_string(void);
int32_t kt_inline_restrict(void);
int32_t kt_callback_throws(void);

static int s_wrong;
static void check(const char *what, int32_t v, int32_t want)
{
    kmicro_puts(what);
    kmicro_put_int(v);
    kmicro_puts(v == want ? "  OK\n" : "  WRONG\n");
    s_wrong += v != want;
}

int main(void)
{
    kmicro_init();
#if defined(TEST_CALLBACK_THROWS)              /* the case run_all builds with TEST_CALLBACK_THROWS: exit 98 */
    check("callbackThrows() = ", kt_callback_throws(), -7);
    return 1;
#endif
    check("global() = ", kt_global(), 15);
    check("structReturn() = ", kt_struct_return(), 34);
    check("structArg() = ", kt_struct_arg(), 42);
    check("floatStructReturn() = ", kt_float_struct_return(), 407);
    check("doubleStructReturn() = ", kt_double_struct_return(), 1225);
    check("floatStructCallback() = ", kt_float_struct_callback(), 295);
    check("callback() = ", kt_callback(), 42);
    check("sortDescending() = ", kt_sort_descending(), 97531);
    check("varargs() = ", kt_varargs(), 6);
    check("inlineLoop() = ", kt_inline_loop(), 10);
    check("inlineAsm() = ", kt_inline_asm(), 42);
    check("inlineString() = ", kt_inline_string(), 1);
    check("inlineRestrict() = ", kt_inline_restrict(), 18);
    check("drv_counter = ", drv_counter, 15);
    kmicro_puts(s_wrong ? "cinterop_shapes: WRONG\n" : "cinterop_shapes: all OK\n");
    return s_wrong ? 1 : 0;
}
