/* Bare-metal start for the QEMU harness: vector table, FPU on, .data/.bss init, init_array, main, semihosting exit. */
#include <stdint.h>
#include <string.h>

extern uint32_t _estack, _sidata, _sdata, _edata, _sbss, _ebss;
extern void (*__init_array_start[])(void), (*__init_array_end[])(void);
int main(void);
void kmicro_exit(int code);

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
    for (void (**f)(void) = __init_array_start; f < __init_array_end; f++)
        (*f)();
    kmicro_exit(run_main());
    for (;;) {
    }
}

static void fault(void) { kmicro_exit(99); }
void HardFault_Handler(void) __attribute__((alias("fault")));

static void no_tick(void) {}
void SysTick_Handler(void) __attribute__((weak, alias("no_tick")));

__attribute__((section(".isr_vector"), used))
const void *const vectors[16] = { &_estack, Reset_Handler, fault, HardFault_Handler, fault, fault, fault,
                                   0, 0, 0, 0, fault, fault, 0, fault, SysTick_Handler };

/* ARM semihosting (QEMU -semihosting). */
static int semi(int op, void *arg)
{
    register int r0 __asm("r0") = op;
    register void *r1 __asm("r1") = arg;
    __asm volatile("bkpt 0xAB" : "+r"(r0) : "r"(r1) : "memory");
    return r0;
}
void kmicro_puts(const char *s) { semi(0x04, (void *)s); }     /* SYS_WRITE0 */
void kmicro_exit(int code)
{
    uint32_t args[2] = { 0x20026u, (uint32_t)code };          /* ADP_Stopped_ApplicationExit, exit code */
    semi(0x20, args);                                           /* SYS_EXIT_EXTENDED */
    for (;;) {
    }
}
