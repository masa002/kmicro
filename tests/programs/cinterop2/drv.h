/* A C driver API in the shapes vendor headers use: structs by value, callbacks, globals and varargs. Kotlin calls
 * it through cinterop (drv.def, package drv); tests/programs/cinterop2/drv.c implements it. */
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

#endif
