/* Bare-metal start for unit tests on QEMU mps2-an386: a firmware's C tests linked with its Kotlin modules.
 * Vector table, FPU on, .data/.bss, constructors, newlib's semihosting stdio (rdimon), the kmicro runtime, the
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
    initialise_monitor_handles();
    for (void (**f)(void) = __init_array_start; f < __init_array_end; f++)
        (*f)();
    kmicro_init();
    int r = run_main();
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
