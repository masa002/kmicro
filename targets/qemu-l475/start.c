/* Bare-metal start for the QEMU harness: vector table, FPU on, .data/.bss init, MPU stack guard, init_array, main,
 * semihosting output and exit, a fault report. */
#include <stdint.h>
#include <string.h>

extern uint32_t _estack, _sidata, _sdata, _edata, _sbss, _ebss, _sguard, _eguard;
extern void (*__init_array_start[])(void), (*__init_array_end[])(void);
int main(void);
void kmicro_exit(int code);
void kmicro_puts(const char *s);
void kmicro_put_int(int32_t v);

#define SCB_SHCSR (*(volatile uint32_t *)0xE000ED24)
#define SCB_CFSR  (*(volatile uint32_t *)0xE000ED28)
#define SCB_HFSR  (*(volatile uint32_t *)0xE000ED2C)
#define SCB_MMFAR (*(volatile uint32_t *)0xE000ED34)
#define SCB_BFAR  (*(volatile uint32_t *)0xE000ED38)
#define MPU_CTRL  (*(volatile uint32_t *)0xE000ED94)
#define MPU_RBAR  (*(volatile uint32_t *)0xE000ED9C)
#define MPU_RASR  (*(volatile uint32_t *)0xE000EDA0)
#define MPU_NO_ACCESS(log2_size) ((1u << 28) | (((log2_size) - 1u) << 1) | 1u)   /* XN, AP=000, SIZE, ENABLE */

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

/* MPU region 1: the 256 bytes between .bss and the stack (l475.ld), no access. An overflowing stack faults there
 * before it writes .bss, which holds the Kotlin heap and the runtime's globals. PRIVDEFENA keeps the default memory
 * map everywhere else. A frame larger than the guard can still jump it. */
static void mpu_guards(void)
{
    MPU_RBAR = (uint32_t)&_sguard | 0x10u | 1u;                 /* VALID, region 1 */
    MPU_RASR = MPU_NO_ACCESS(8);                                /* 256 bytes */
    MPU_CTRL = 5u;                                              /* ENABLE, PRIVDEFENA */
    __asm volatile("dsb\n isb");
}

/* main in a function of its own: whatever LTO inlines into it, start_c keeps a small frame, so clearing .bss can
 * never clear start_c's own stack. */
__attribute__((noinline)) static int run_main(void) { return main(); }

__attribute__((noinline, used, noreturn)) void start_c(void)
{
    memcpy(&_sdata, &_sidata, (size_t)((char *)&_edata - (char *)&_sdata));
    memset(&_sbss, 0, (size_t)((char *)&_ebss - (char *)&_sbss));
    SCB_SHCSR |= 7u << 16;                                      /* MemManage, BusFault, UsageFault handlers on */
    mpu_guards();
    for (void (**f)(void) = __init_array_start; f < __init_array_end; f++)
        (*f)();
    kmicro_exit(run_main());
    for (;;) {
    }
}

/* ---- faults: a report, then exit 99 ----
 * The entry is naked: it takes the stacked frame (MSP or PSP, by EXC_RETURN) and moves SP to a stack of its own
 * before any C runs, because the faulting stack may be the problem. The report reads the stacked PC and LR only when
 * the frame lies in RAM outside the guard; tools/symbolize.py resolves its "at 0x..." address. */
__attribute__((used)) uint64_t start_fault_stack[32];          /* 256 bytes, in .bss: below the guard */

static void put_hex(const char *label, uint32_t v)
{
    char b[11] = "0x";
    for (int i = 0; i < 8; i++) {
        unsigned d = (v >> (28 - 4 * i)) & 0xFu;
        b[2 + i] = (char)(d < 10u ? '0' + d : 'a' + d - 10u);
    }
    b[10] = 0;
    kmicro_puts(label);
    kmicro_puts(b);
}

static int within(uintptr_t a, uintptr_t lo, uintptr_t hi) { return a >= lo && a < hi; }

__attribute__((used, noreturn)) void start_fault(const uint32_t *frame)
{
    static const char *const names[] = { 0, 0, "NMI", "HardFault", "MemManage", "BusFault", "UsageFault" };
    uint32_t ipsr, cfsr = SCB_CFSR, mmfar = SCB_MMFAR;
    __asm volatile("mrs %0, ipsr" : "=r"(ipsr));
    ipsr &= 0x1FFu;
    uintptr_t f = (uintptr_t)frame, gs = (uintptr_t)&_sguard, ge = (uintptr_t)&_eguard;
    uintptr_t fs = (uintptr_t)start_fault_stack;
    int readable = f % 4u == 0u && (within(f, (uintptr_t)&_sdata, gs - 31u) || within(f, ge, (uintptr_t)&_estack - 31u));
    int overflow = (cfsr & ((1u << 4) | (1u << 12))) != 0u                  /* MSTKERR, STKERR: stacking failed */
                   || ((cfsr & (1u << 7)) && within(mmfar, gs, ge))          /* a store into the guard */
                   || (f < ge && !within(f, fs, fs + sizeof start_fault_stack));  /* SP in the guard or past it */
    kmicro_puts("kmicro fault: ");
    if (overflow)
        kmicro_puts("stack overflow (");
    if (ipsr >= 2u && ipsr <= 6u) {
        kmicro_puts(names[ipsr]);
    } else {
        kmicro_puts("exception ");
        kmicro_put_int((int32_t)ipsr);
    }
    if (overflow)
        kmicro_puts(")");
    if (readable)
        put_hex(" at ", frame[6]);                                 /* the stacked PC */
    else
        kmicro_puts(", no stacked frame");
    put_hex("\n    sp ", (uint32_t)f);
    if (readable)
        put_hex("  lr ", frame[5]);
    put_hex("  cfsr ", cfsr);
    put_hex("  hfsr ", SCB_HFSR);
    put_hex("  mmfar ", mmfar);
    put_hex("  bfar ", SCB_BFAR);
    kmicro_puts("\n");
    kmicro_exit(99);
    for (;;) {
    }
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
