@file:OptIn(kotlinx.cinterop.ExperimentalForeignApi::class)
package irq

import c.*                          // support/hw.h through support/hw.def: hw_rd32, hw_wr32, hw_wfi, hw_irq_save ...
import kotlin.concurrent.Volatile

// Written by the interrupt handler and read by the main loop: @Volatile makes every access a real load or store.
// kt_init_all() (kbuild --init-all) creates this file's globals at boot, so the handler never initialises them.
@Volatile private var ticks = 0
@Volatile private var flagged = 0
@Volatile private var last = 0

// The SysTick interrupt handler. irq.h declares `void SysTick_Handler(void)`, and kbuild --c-api gives this function
// that C name, so the vector table calls it directly. A handler must not allocate: primitives and hw_* calls only
// (docs/writing-kotlin.md), which tools/isr_check.py checks in the machine code.
fun sysTickHandler() {
    val t = ticks + 1
    ticks = t
    if ((hw_rd32(SysTick.CTRL) and SysTick_CTRL_COUNTFLAG_Msk).toInt() != 0) flagged++   // reading CTRL clears it
    if (t == last) hw_wr32(SysTick.CTRL, 0u)            // the last tick stops the timer
}

// Runs SysTick at 1 kHz for n interrupts, sleeping (WFI) between them, and returns the ticks counted.
fun runTicks(n: Int): Int {
    last = n
    hw_wr32(SysTick.LOAD, 4_000u - 1u)                  // 1 ms at the 4 MHz clock an STM32L4 starts with
    hw_wr32(SysTick.VAL, 0u)
    hw_wr32(SysTick.CTRL, SysTick_CTRL_CLKSOURCE_Msk or SysTick_CTRL_TICKINT_Msk or SysTick_CTRL_ENABLE_Msk)
    while (true) {
        val primask = hw_irq_save()     // interrupts off: the last tick cannot slip in between the check and WFI
        if (ticks >= n) {
            hw_irq_restore(primask)
            break
        }
        hw_wfi()                        // a pending interrupt still wakes the core ...
        hw_irq_restore(primask)         // ... and its handler runs here
    }
    println("SysTick: $ticks ticks, COUNTFLAG set in $flagged of them")
    return ticks
}
