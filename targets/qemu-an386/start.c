/* Bare-metal start for QEMU mps2-an386, the target with megabytes of memory: Kotlin modules compiled exactly as for
 * the device, linked with C code that needs more RAM than the device has (a test that models a large peripheral in
 * memory, for example). Vector table, FPU on, .data/.bss, constructors, newlib's semihosting stdio (rdimon), the
 * kmicro runtime, the program's main(), a fault report, an exit that carries the status back to QEMU
 * (SYS_EXIT_EXTENDED), and the host's clocks for kotlin.time. */
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "kmicro.h"

extern uint32_t _estack, _sidata, _sdata, _edata, _sbss, _ebss;
extern void (*__init_array_start[])(void), (*__init_array_end[])(void);
extern void initialise_monitor_handles(void);
int main(void);
void kmicro_exit(int code) __attribute__((noreturn));

/* The FPU goes on before any compiled C code runs. With LTO, main and the Kotlin code it calls can be inlined into
 * the C start function, whose prologue then saves FP registers (vpush): with CP10/CP11 still off that is a fault. */
__attribute__((naked)) void Reset_Handler(void)
{
    __asm volatile("movw r0, #0xED88\n"
                   "movt r0, #0xE000\n"                         /* CPACR */
                   "ldr r1, [r0]\n"
                   "orr r1, r1, #(0xF << 20)\n"                  /* CP10/CP11 full access (FPU) */
                   "str r1, [r0]\n"
                   "dsb\n"
                   "isb\n"
                   "b start_c\n");
}

/* main in a function of its own: whatever LTO inlines into it, start_c keeps a small frame, so clearing .bss can
 * never clear start_c's own stack. */
__attribute__((noinline)) static int run_main(void) { return main(); }

__attribute__((noinline, used, noreturn)) void start_c(void)
{
    memcpy(&_sdata, &_sidata, (size_t)((char *)&_edata - (char *)&_sdata));
    memset(&_sbss, 0, (size_t)((char *)&_ebss - (char *)&_sbss));
    *(volatile uint32_t *)0xE000ED24 |= 7u << 16;              /* SHCSR: MemManage, BusFault, UsageFault handlers on */
    initialise_monitor_handles();
    for (void (**f)(void) = __init_array_start; f < __init_array_end; f++)
        (*f)();
    kmicro_init();
    int r = run_main();
    fflush(stdout);
    fflush(stderr);
    kmicro_exit(r);
}

static int semi(int op, void *arg)
{
    register int r0 __asm("r0") = op;
    register void *r1 __asm("r1") = arg;
    __asm volatile("bkpt 0xAB" : "+r"(r0) : "r"(r1) : "memory");
    return r0;
}

/* ---- faults: a report, then exit 99 ----
 * The entry is naked: it takes the stacked frame (MSP or PSP, by EXC_RETURN) and moves SP to a stack of its own
 * before any C runs, because the faulting stack may be the problem. The report reads the stacked PC and LR only when
 * the frame lies in RAM; tools/symbolize.py resolves its "at 0x..." address. It writes through semihosting directly:
 * the fault may have hit inside newlib's stdio. */
#define SCB_CFSR  (*(volatile uint32_t *)0xE000ED28)
#define SCB_HFSR  (*(volatile uint32_t *)0xE000ED2C)
#define SCB_MMFAR (*(volatile uint32_t *)0xE000ED34)
#define SCB_BFAR  (*(volatile uint32_t *)0xE000ED38)

__attribute__((used)) uint64_t start_fault_stack[32];          /* 256 bytes */

static void fault_puts(const char *s) { semi(0x04, (void *)s); }  /* SYS_WRITE0 */

static void put_hex(const char *label, uint32_t v)
{
    char b[11] = "0x";
    for (int i = 0; i < 8; i++) {
        unsigned d = (v >> (28 - 4 * i)) & 0xFu;
        b[2 + i] = (char)(d < 10u ? '0' + d : 'a' + d - 10u);
    }
    b[10] = 0;
    fault_puts(label);
    fault_puts(b);
}

__attribute__((used, noreturn)) void start_fault(const uint32_t *frame)
{
    static const char *const names[] = { 0, 0, "NMI", "HardFault", "MemManage", "BusFault", "UsageFault" };
    uint32_t ipsr;
    __asm volatile("mrs %0, ipsr" : "=r"(ipsr));
    ipsr &= 0x1FFu;
    uintptr_t f = (uintptr_t)frame;
    int readable = f % 4u == 0u && f >= (uintptr_t)&_sdata && f <= (uintptr_t)&_estack - 32u;
    fault_puts("kmicro fault: ");
    if (ipsr >= 2u && ipsr <= 6u)
        fault_puts(names[ipsr]);
    else
        put_hex("exception ", ipsr);
    if (readable)
        put_hex(" at ", frame[6]);                                 /* the stacked PC */
    else
        fault_puts(", no stacked frame");
    put_hex("\n    sp ", (uint32_t)f);
    if (readable)
        put_hex("  lr ", frame[5]);
    put_hex("  cfsr ", SCB_CFSR);
    put_hex("  hfsr ", SCB_HFSR);
    put_hex("  mmfar ", SCB_MMFAR);
    put_hex("  bfar ", SCB_BFAR);
    fault_puts("\n");
    kmicro_exit(99);
}

__attribute__((naked)) static void fault(void)
{
    __asm volatile("tst lr, #4\n"
                   "ite eq\n"
                   "mrseq r0, msp\n"
                   "mrsne r0, psp\n"
                   "movw r1, #:lower16:start_fault_stack + 256\n"
                   "movt r1, #:upper16:start_fault_stack + 256\n"
                   "mov sp, r1\n"
                   "b start_fault\n");
}

__attribute__((section(".isr_vector"), used))
const void *const vectors[16] = { &_estack, Reset_Handler, fault, fault, fault, fault, fault };

/* Not through stdout: newlib's streams write through the runtime's _write, which calls this function. */
void kmicro_puts(const char *s) { semi(0x04, (void *)s); }     /* SYS_WRITE0 */

void kmicro_exit(int code)
{
    uint32_t args[2] = { 0x20026u, (uint32_t)code };          /* ADP_Stopped_ApplicationExit, status */
    semi(0x20, args);                                          /* SYS_EXIT_EXTENDED */
    for (;;) {
    }
}

/* ---- clocks for kotlin.time and kotlin.random (the hooks in kmicro.h): the host's clocks through semihosting, so
 * SysTick stays free for the program ---- */
int64_t kmicro_time_ns(void)
{
    static uint32_t s_hz;
    uint32_t t[2];
    if (s_hz == 0u)
        s_hz = (uint32_t)semi(0x31, 0);                         /* SYS_TICKFREQ */
    if (s_hz == 0u || s_hz == 0xFFFFFFFFu || semi(0x30, t) != 0)   /* SYS_ELAPSED */
        kmicro_panic("semihosting SYS_ELAPSED / SYS_TICKFREQ failed");
    uint64_t ticks = (uint64_t)t[1] << 32 | t[0];
    return (int64_t)(ticks / s_hz * 1000000000u + ticks % s_hz * 1000000000u / s_hz);
}

int64_t kmicro_wall_time_ns(void)
{
    static int64_t s_offset;                                    /* wall clock minus monotonic clock, taken once */
    if (s_offset == 0)
        s_offset = (int64_t)(uint32_t)semi(0x11, 0) * 1000000000 - kmicro_time_ns();   /* SYS_TIME: whole seconds */
    return s_offset + kmicro_time_ns();
}

uint64_t kmicro_random_seed(void) { return (uint64_t)kmicro_time_ns(); }   /* a different Random.Default each run */

/* newlib's __libc_init_array / __libc_fini_array call these (crti/crtn are not linked). */
void _init(void) {}
void _fini(void) {}

/* newlib's exit() ends in _exit(): keep the status (linked with --wrap=_exit). */
void __wrap__exit(int code) __attribute__((noreturn));
void __wrap__exit(int code)
{
    fflush(stdout);
    kmicro_exit(code);
}
