/* The C side of the event loop (event_loop.kt) on QEMU: a 1 kHz SysTick clock, injected button presses, WFI between
 * steps. */
#include "kmicro.h"
#include <stdint.h>

void kt_start(void);                            /* Kotlin: @CName("kt_start") fun startApp() */
int32_t kt_step(int32_t events, int32_t now);   /* Kotlin: @CName("kt_step") fun step(events: Int, nowMs: Int): Int */
int32_t kt_result(void);                        /* Kotlin: @CName("kt_result") fun result(): Int */

static volatile uint32_t s_ms;
static volatile uint32_t s_events;
void SysTick_Handler(void)
{
    s_ms++;
    if (s_ms == 1200 || s_ms == 2300)           /* the "button" presses */
        s_events |= 1u;
}

#define SYST_CSR (*(volatile uint32_t *)0xE000E010)
#define SYST_RVR (*(volatile uint32_t *)0xE000E014)
#define SYST_CVR (*(volatile uint32_t *)0xE000E018)

int main(void)
{
    kmicro_init();
    SYST_RVR = 4000u - 1u;                       /* 1 ms at the 4 MHz clock (MSI) the STM32L4 and QEMU's model start with */
    SYST_CVR = 0;
    SYST_CSR = 7u;                               /* enable, interrupt, processor clock */
    kt_start();
    uint32_t steps = 0, sleeps = 0;
    while (s_ms < 3000u) {
        __asm volatile("cpsid i");
        uint32_t ev = s_events;
        s_events = 0;
        __asm volatile("cpsie i");
        int32_t next = kt_step((int32_t)ev, (int32_t)s_ms);
        steps++;
        if (next == 0)
            continue;
        /* every coroutine waits: sleep until the next timer or an event (the device enters Stop 1 here) */
        uint32_t until = next < 0 ? 0xFFFFFFFFu : s_ms + (uint32_t)next;
        while (s_ms < until && s_ms < 3000u) {
            __asm volatile("cpsid i");
            if (s_events) { __asm volatile("cpsie i"); break; }
            __asm volatile("wfi\n cpsie i");     /* a pending interrupt still wakes the core */
            sleeps++;
        }
    }
    int32_t r = kt_result();
    kmicro_puts("event loop: ticks*100+presses = "); kmicro_put_int(r);
    kmicro_puts("   steps "); kmicro_put_int((int32_t)steps);
    kmicro_puts(", WFI sleeps "); kmicro_put_int((int32_t)sleeps);
    kmicro_puts(r == 502 ? "  OK\n" : "  WRONG (expected 502)\n");
    return r == 502 ? 0 : 1;
}
