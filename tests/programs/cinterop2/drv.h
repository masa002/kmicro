/* A C driver API in the shapes vendor headers use: structs by value, callbacks, globals, varargs and static inline
 * helpers. Kotlin calls it through cinterop (drv.def, package drv); tests/programs/cinterop2/drv.c implements it. */
#ifndef DRV_H
#define DRV_H
#include <stdint.h>

extern int32_t drv_counter;                     /* a C global Kotlin reads and writes */

typedef struct { int32_t x, y; } pt_t;
pt_t pt_make(int32_t x, int32_t y);             /* a struct returned by value */
int32_t pt_sum(pt_t p);                         /* a struct passed by value */

typedef int32_t (*drv_cb_t)(int32_t);
void drv_set_cb(drv_cb_t cb);                   /* the driver keeps a callback ... */
int32_t drv_fire(int32_t v);                    /* ... and calls it later */
void drv_sort(int32_t *v, int32_t n, int (*cmp)(const void *, const void *));       /* qsort with a comparator */

int32_t sum_va(int32_t n, ...);                 /* varargs */

uint32_t plain_fn(uint32_t v);

/* static inline helpers, compiled into the program by cinterop: a loop, an immediate in inline assembly and a
 * string constant with a '#' in it */
static inline uint32_t sum_to(uint32_t n)
{
    uint32_t s = 0;
    for (uint32_t i = 1; i <= n; i++)
        s += plain_fn(i);
    return s;
}

static inline uint32_t add_one_asm(uint32_t v)
{
    uint32_t r;
    __asm__("add %0, %1, #1" : "=r"(r) : "r"(v));
    return r;
}

static inline const char *slot_name(void) { return "slot #1"; }

#endif
