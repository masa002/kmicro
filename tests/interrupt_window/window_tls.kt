@file:OptIn(kotlin.experimental.ExperimentalNativeApi::class)

package window

import kotlin.native.CName
import kotlin.native.concurrent.ThreadLocal

// The same as window.kt with @ThreadLocal globals, which the compiler initialises through another runtime function.
@ThreadLocal
val firstLocal = pendTick()

@ThreadLocal
val limitLocal = firstLocal + 3000

@CName("w_thread_use_local")
fun threadUseLocal(): Int = limitLocal

@CName("w_handler_use_local")
fun handlerUseLocal(): Int = limitLocal
