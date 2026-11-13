@file:OptIn(kotlinx.cinterop.ExperimentalForeignApi::class, kotlin.experimental.ExperimentalNativeApi::class)

package window

import c.hw_isb
import c.hw_wr32
import kotlin.native.CName

// The initializer of the first global pends SysTick, so the handler runs while the thread code is still creating
// this file's globals: `limit` is not set yet. The runtime must stop the program instead of letting the handler read 0.
val first = pendTick()
val limit = first + 3000

fun pendTick(): Int {
    hw_wr32(0xE000ED04u, 1u shl 26)     // ICSR.PENDSTSET: SysTick is taken before the next instruction
    hw_isb()
    return 1
}

@CName("w_thread_use")
fun threadUse(): Int = limit

@CName("w_handler_use")
fun handlerUse(): Int = limit
