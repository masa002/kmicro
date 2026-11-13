/* The selftest on an STM32L431 (Cortex-M4F, 256 KB flash, 64 KB SRAM): start-up code, a 16 MHz clock, USART1 for
 * kmicro_puts, and the checks of ../main.c, each one timed with the Cortex-M4 cycle counter.
 *
 *   clock    SYSCLK = MSI at 16 MHz (range 8); flash with 0 wait states (enough up to 16 MHz in voltage range 1),
 *            prefetch and both caches
 *   output   USART1, TX on PA9 and RX on PA10 (AF7), 115200 8N1, clocked by HSI16
 *   timing   the DWT cycle counter around each check, printed in microseconds (cycles / 16)
 *
 * No interrupt is enabled. The program prints its report, then "kmicro: stopped, code N" (N = failed checks), and
 * waits. A fault prints the exception number, PC, LR and CFSR, and waits too. Registers are written by address
 * (from RM0394, the STM32L4 reference manual), so the example needs no device header.
 *
 * The checks and their labels are those of ../main.c: change both together. build.py builds this file. */
#include <stdbool.h>
#include <stdint.h>
#include <string.h>
#include "kmicro.h"
#include "selftest.h"

#define REG(addr) (*(volatile uint32_t *)(addr))

#define RCC_CR       REG(0x40021000u)
#define RCC_CFGR     REG(0x40021008u)
#define RCC_AHB2ENR  REG(0x4002104Cu)
#define RCC_APB1ENR1 REG(0x40021058u)
#define RCC_APB2ENR  REG(0x40021060u)
#define RCC_CCIPR    REG(0x40021088u)
#define FLASH_ACR    REG(0x40022000u)
#define PWR_CR1      REG(0x40007000u)
#define PWR_SR2      REG(0x40007014u)
#define GPIOA_MODER  REG(0x48000000u)
#define GPIOA_PUPDR  REG(0x4800000Cu)
#define GPIOA_AFRH   REG(0x48000024u)
#define USART1_CR1   REG(0x40013800u)
#define USART1_BRR   REG(0x4001380Cu)
#define USART1_ISR   REG(0x4001381Cu)
#define USART1_TDR   REG(0x40013828u)
#define SCB_VTOR     REG(0xE000ED08u)
#define SCB_CFSR     REG(0xE000ED28u)
#define DEMCR        REG(0xE000EDFCu)
#define DWT_CTRL     REG(0xE0001000u)
#define DWT_CYCCNT   REG(0xE0001004u)

#define CLOCK_HZ 16000000u                          /* SYSCLK and HSI16 */
#define BAUD     115200u

extern uint32_t _estack, _sidata, _sdata, _edata, _sbss, _ebss;
extern void (*__init_array_start[])(void), (*__init_array_end[])(void);
extern const void *const vectors[16];
int main(void);
void Reset_Handler(void);
__attribute__((noreturn)) void board_start(void);
__attribute__((noreturn)) void board_fault(const uint32_t *frame, uint32_t ipsr);
__attribute__((noreturn)) void kmicro_exit(int code);

/* ---- clock and UART ---- */

/* Ready flags come within microseconds; a bounded wait never hangs the start-up on a flag that does not come. */
static void wait_bits(volatile uint32_t *reg, uint32_t mask, uint32_t value)
{
    for (uint32_t i = 0; i < 20000u && (*reg & mask) != value; i++) {
    }
}

static void clock_init(void)
{
    RCC_APB1ENR1 |= 1u << 28;                       /* PWREN */
    (void)RCC_APB1ENR1;
    PWR_CR1 = (PWR_CR1 & ~(3u << 9)) | (1u << 9);   /* voltage range 1 (the reset value): 16 MHz with 0 wait states */
    wait_bits(&PWR_SR2, 1u << 10, 0u);              /* VOSF */
    RCC_CR |= 1u;                                   /* MSION */
    wait_bits(&RCC_CR, 1u << 1, 1u << 1);           /* MSIRDY */
    RCC_CFGR &= ~3u;                                /* SYSCLK = MSI, in case a boot loader left another clock */
    wait_bits(&RCC_CFGR, 3u << 2, 0u);              /* SWS */
    RCC_CR = (RCC_CR & ~(0xFu << 4)) | (8u << 4) | (1u << 3);   /* MSIRANGE 8 = 16 MHz, MSIRGSEL */
    wait_bits(&RCC_CR, 1u << 1, 1u << 1);
    FLASH_ACR = (FLASH_ACR & ~7u) | (1u << 8) | (1u << 9) | (1u << 10);   /* 0 wait states, PRFTEN, ICEN, DCEN */
    wait_bits(&FLASH_ACR, 7u, 0u);
    RCC_CFGR &= ~((0xFu << 4) | (7u << 8) | (7u << 11));        /* AHB, APB1 and APB2 not divided */
    RCC_CR |= 1u << 8;                              /* HSION: the USART1 clock */
    wait_bits(&RCC_CR, 1u << 10, 1u << 10);         /* HSIRDY */
}

static void uart_init(void)
{
    RCC_AHB2ENR |= 1u;                              /* GPIOA */
    RCC_APB2ENR |= 1u << 14;                        /* USART1 */
    (void)RCC_APB2ENR;
    GPIOA_AFRH = (GPIOA_AFRH & ~0xFF0u) | (7u << 4) | (7u << 8);      /* PA9, PA10: AF7 = USART1 */
    GPIOA_PUPDR = (GPIOA_PUPDR & ~(3u << 20)) | (1u << 20);            /* pull-up on RX */
    GPIOA_MODER = (GPIOA_MODER & ~(0xFu << 18)) | (0xAu << 18);       /* PA9, PA10: alternate function */
    RCC_CCIPR = (RCC_CCIPR & ~3u) | 2u;             /* USART1SEL = HSI16 */
    USART1_CR1 = 0u;
    USART1_BRR = (CLOCK_HZ + BAUD / 2u) / BAUD;     /* 139 */
    USART1_CR1 = (1u << 3) | (1u << 2) | 1u;        /* TE, RE, UE */
}

static void tx(char c)
{
    while (!(USART1_ISR & (1u << 7))) {             /* TXE */
    }
    USART1_TDR = (uint8_t)c;
}

/* Returns when the last character has left (TC), so a timed check includes the time to send what it printed. */
void kmicro_puts(const char *s)
{
    for (; *s; s++) {
        if (*s == '\n')
            tx('\r');
        tx(*s);
    }
    while (!(USART1_ISR & (1u << 6))) {             /* TC */
    }
}

__attribute__((noreturn)) void kmicro_exit(int code)
{
    kmicro_puts("\nkmicro: stopped, code ");
    kmicro_put_int(code);
    kmicro_puts("\n");
    for (;;)
        __asm volatile("wfi");
}

/* ---- faults ---- */

static void put_hex(const char *label, uint32_t v)
{
    char b[11] = "0x";
    for (int i = 0; i < 8; i++)
        b[2 + i] = "0123456789abcdef"[(v >> (28 - 4 * i)) & 0xFu];
    b[10] = 0;
    kmicro_puts(label);
    kmicro_puts(b);
}

__attribute__((used, noreturn)) void board_fault(const uint32_t *frame, uint32_t ipsr)
{
    kmicro_puts("\nfault: exception ");
    kmicro_put_int((int32_t)(ipsr & 0x1FFu));
    put_hex(" pc=", frame[6]);
    put_hex(" lr=", frame[5]);
    put_hex(" cfsr=", SCB_CFSR);
    kmicro_puts("\n");
    for (;;)
        __asm volatile("wfi");
}

/* The stacked frame is on MSP or PSP, as EXC_RETURN (LR) says. */
__attribute__((naked)) static void fault_entry(void)
{
    __asm volatile("tst lr, #4\n"
                   "ite eq\n"
                   "mrseq r0, msp\n"
                   "mrsne r0, psp\n"
                   "mrs r1, ipsr\n"
                   "b board_fault\n");
}

/* ---- start-up ---- */

/* The FPU goes on before any compiled C runs: with LTO, code that uses FP registers can be inlined into the C start
 * function, whose prologue would then save them while CP10/CP11 are still off. */
__attribute__((naked)) void Reset_Handler(void)
{
    __asm volatile("movw r0, #0xED88\n"
                   "movt r0, #0xE000\n"             /* CPACR */
                   "ldr r1, [r0]\n"
                   "orr r1, r1, #(0xF << 20)\n"     /* CP10/CP11 full access */
                   "str r1, [r0]\n"
                   "dsb\n"
                   "isb\n"
                   "b board_start\n");
}

/* main in a function of its own, so that whatever LTO inlines into it never enlarges board_start's frame. */
__attribute__((noinline)) static int run_main(void) { return main(); }

__attribute__((used, noinline, noreturn)) void board_start(void)
{
    memcpy(&_sdata, &_sidata, (size_t)((char *)&_edata - (char *)&_sdata));
    memset(&_sbss, 0, (size_t)((char *)&_ebss - (char *)&_sbss));
    SCB_VTOR = (uint32_t)vectors;
    DEMCR |= 1u << 24;                              /* TRCENA: DWT on */
    DWT_CYCCNT = 0u;
    DWT_CTRL |= 1u;                                 /* CYCCNTENA */
    clock_init();
    uart_init();
    for (void (**f)(void) = __init_array_start; f < __init_array_end; f++)
        (*f)();                                     /* registers the Kotlin module initializers */
    kmicro_exit(run_main());
}

__attribute__((section(".isr_vector"), used))
const void *const vectors[16] = {
    &_estack, (const void *)Reset_Handler,
    (const void *)fault_entry, (const void *)fault_entry, (const void *)fault_entry,   /* NMI, HardFault, MemManage */
    (const void *)fault_entry, (const void *)fault_entry,                              /* BusFault, UsageFault */
    0, 0, 0, 0,
    (const void *)fault_entry, (const void *)fault_entry, 0,                           /* SVCall, DebugMonitor */
    (const void *)fault_entry, (const void *)fault_entry,                              /* PendSV, SysTick */
};

/* ---- the checks of ../main.c, timed ---- */

static int s_fail;

static void report(const char *name, bool ok, uint32_t cycles)
{
    kmicro_puts(ok ? "  PASS  " : "  FAIL  ");
    kmicro_puts(name);
    kmicro_puts("   ");
    kmicro_put_int((int32_t)(cycles / (CLOCK_HZ / 1000000u)));
    kmicro_puts(" us\n");
    if (!ok)
        s_fail++;
}

#define TIMED(name, check)                                                                                        \
    do {                                                                                                          \
        uint32_t t0_ = DWT_CYCCNT;                                                                                \
        bool ok_ = (check);                                                                                       \
        report(name, ok_, DWT_CYCCNT - t0_);                                                                      \
    } while (0)

/* kmicro_init() runs the module initializers (the compiler registers them through .init_array, which LTO usually
 * resolves at link time). The standard library's modules register their thread-local slots there, so no slot means
 * that no initializer ran. */
static bool runtime_init(void)
{
    kmicro_init();
    return kmicro_tls_slot_count > 0;
}

static bool gc_check(void)
{
    const int32_t rounds = 60;          /* gc_chains sums every node it built: 100-node chains, survivors, array */
    int32_t expect = rounds * 4950 + rounds * (rounds - 1) / 2 + 50 * 49 / 2;
    for (int32_t k = 0; k < rounds; k += 7)
        expect += k * 1000;
    return gc_chains(rounds) == expect;
}

static bool coroutine_check(void)
{
    coro_start();                       /* the coroutine suspends at once and waits for events */
    int32_t sum = 0, bad = 0;
    for (int32_t i = 1; i <= 300; i++) {
        sum += i;
        if (coro_event(i) != sum)
            bad++;
    }
    return bad == 0;
}

/* One collection more, and the garbage left by the checks before it is gone. */
static bool full_gc(void)
{
    kmicro_stats_t before, after;
    kmicro_stats(&before);
    kmicro_gc();
    kmicro_stats(&after);
    return after.gc_count == before.gc_count + 1 && after.used_bytes < before.used_bytes;
}

static void stat(const char *name, uint32_t v)
{
    kmicro_puts(name);
    kmicro_put_int((int32_t)v);
}

int main(void)
{
    kmicro_puts("\n=== kmicro self-test: official Kotlin/Native 2.4.21 output on STM32L431 ===\n");
    TIMED("runtime init (module initializers)", runtime_init());
    TIMED("println from Kotlin", hello() == 0);
    TIMED("classes, interface, virtual calls (= 45)", shapes(5) == 45);
    TIMED("garbage collection, 6000+ objects", gc_check());
    TIMED("strings (10 checks, UTF-16, JVM hashCode)", strings(2500) == 0);
    TIMED("exceptions (10 checks, 200+ throws)", exceptions(-3) == 0);
    TIMED("one throw + catch", throw_once(-1) == 1);
    TIMED("coroutine: 300 suspend/resume cycles", coroutine_check());
    TIMED("one full GC", full_gc());

    kmicro_stats_t st;
    kmicro_stats(&st);
    stat("\nheap ", st.heap_bytes);
    stat(" B, peak ", st.peak_bytes);
    stat(" B, live peak ", st.live_peak_bytes);
    stat(" B, objects ", st.alloc_count);
    stat(", collections ", st.gc_count);
    stat(", freed ", st.objects_freed);
    kmicro_puts(s_fail == 0 ? "\nresult: ALL PASS\n" : "\nresult: FAILURES\n");
    return s_fail;
}
