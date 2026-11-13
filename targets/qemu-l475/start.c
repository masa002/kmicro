/* Bare-metal start for the QEMU harness: vector table, .data/.bss init, FPU on, init_array, main, semihosting exit. */
#include <stdint.h>
#include <string.h>

extern uint32_t _estack, _sidata, _sdata, _edata, _sbss, _ebss;
extern void (*__init_array_start[])(void), (*__init_array_end[])(void);
int main(void);
void kmicro_exit(int code);

void Reset_Handler(void)
{
    memcpy(&_sdata, &_sidata, (size_t)((char *)&_edata - (char *)&_sdata));
    memset(&_sbss, 0, (size_t)((char *)&_ebss - (char *)&_sbss));
    *(volatile uint32_t *)0xE000ED88 |= 0xFu << 20;          /* CPACR: CP10/CP11 full access (FPU) */
    __asm volatile("dsb\n isb");
    for (void (**f)(void) = __init_array_start; f < __init_array_end; f++)
        (*f)();
    kmicro_exit(main());
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
