/* --c-api header cases for tests/unit/test_kn_cproto.py: the comment after each line says whether it is a
   prototype the Kotlin code implements. */
#include <stdint.h>
#include <stdbool.h>
#include "cproto_other.h"                                    /* other_fn: no (another header) */
#define DECLARE_HANDLER(n) void n##_IRQHandler(void)

extern void system_init(void);                               /* yes: extern prototype */
void gpio_set(uint32_t pin);                                 /* yes */
static inline void cpu_nop(void) { __asm volatile("nop"); }  /* no: inline body, and not `volatile` */
static inline void led_on(void) { gpio_set(5u); }            /* no: a call inside a body */
DECLARE_HANDLER(EXTI0);                                      /* yes: EXTI0_IRQHandler */
#if 0
void feature_on(void);                                       /* no: inactive */
#endif
void set_cb2(void (*cb)(void (*inner)(int)));                /* yes: nested function pointers */
int32_t gc_chains(int32_t n);                                /* yes */
typedef void (*cb_t)(void);                                  /* no */
struct point { int x, y; };                                  /* no */
__attribute__((noreturn)) void die(int code);                /* yes */
int32_t gc_chains(int32_t n);                                /* (declared twice: listed once) */
void kt_init_all(void);                                      /* yes (kn.build skips its init_all name) */
#ifdef __cplusplus
extern "C" {
#endif
bool ready(void);                                            /* yes */
#ifdef __cplusplus
}
#endif
