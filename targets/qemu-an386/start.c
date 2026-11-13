/* Bare-metal start for unit tests on QEMU mps2-an386: a firmware's C tests linked with its Kotlin modules.
 * Vector table, .data/.bss, FPU on, constructors, newlib's semihosting stdio (rdimon), the kmicro runtime, the
 * test's main(), and an exit that carries the status back to QEMU (SYS_EXIT_EXTENDED). */
#include <stdint.h>
#include <stdio.h>
#include <string.h>

extern uint32_t _estack, _sidata, _sdata, _edata, _sbss, _ebss;
extern void (*__init_array_start[])(void), (*__init_array_end[])(void);
extern void initialise_monitor_handles(void);
void kmicro_init(void);
int main(void);
void kmicro_exit(int code) __attribute__((noreturn));

void Reset_Handler(void) __attribute__((noreturn));
void Reset_Handler(void)
{
    memcpy(&_sdata, &_sidata, (size_t)((char *)&_edata - (char *)&_sdata));
    memset(&_sbss, 0, (size_t)((char *)&_ebss - (char *)&_sbss));
    *(volatile uint32_t *)0xE000ED88 |= 0xFu << 20;          /* CPACR: CP10/CP11 full access (FPU) */
    __asm volatile("dsb\n isb");
    initialise_monitor_handles();
    for (void (**f)(void) = __init_array_start; f < __init_array_end; f++)
        (*f)();
    kmicro_init();
    int r = main();
    fflush(stdout);
    fflush(stderr);
    kmicro_exit(r);
}

static void fault(void)
{
    static const char msg[] = "start_an386: HardFault\n";
    register int r0 __asm("r0") = 0x04;                      /* SYS_WRITE0 */
    register const void *r1 __asm("r1") = msg;
    __asm volatile("bkpt 0xAB" : "+r"(r0) : "r"(r1) : "memory");
    kmicro_exit(98);
}

__attribute__((section(".isr_vector"), used))
const void *const vectors[16] = { &_estack, Reset_Handler, fault, fault, fault, fault, fault };

static int semi(int op, void *arg)
{
    register int r0 __asm("r0") = op;
    register void *r1 __asm("r1") = arg;
    __asm volatile("bkpt 0xAB" : "+r"(r0) : "r"(r1) : "memory");
    return r0;
}

void kmicro_puts(const char *s) { fputs(s, stdout); }

void kmicro_exit(int code)
{
    uint32_t args[2] = { 0x20026u, (uint32_t)code };          /* ADP_Stopped_ApplicationExit, status */
    semi(0x20, args);                                          /* SYS_EXIT_EXTENDED */
    for (;;) {
    }
}

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
