#pragma once
#include <stdint.h>

/* The Kotlin functions of selftest.kt (package selftest), by C names: gc_chains is selftest.gcChains. */
int32_t hello(void);
int32_t shapes(int32_t n);
int32_t gc_chains(int32_t rounds);
int32_t strings(int32_t n);
int32_t exceptions(int32_t n);
int32_t throw_once(int32_t n);
void coro_start(void);
int32_t coro_event(int32_t t);
