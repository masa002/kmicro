@file:OptIn(kotlin.experimental.ExperimentalNativeApi::class)
import kotlin.coroutines.*
import kotlin.native.CName

// A one-slot "event loop": the C side calls k_event() when the button is pressed; the coroutine waits for it.
private var waiting: Continuation<Int>? = null
private var presses = 0

suspend fun awaitButton(): Int = suspendCoroutine { c -> waiting = c }

suspend fun app() {
    while (true) {
        val t = awaitButton()
        presses += t
    }
}

@CName("k_start")
fun start() {
    ::app.startCoroutine(Continuation(EmptyCoroutineContext) { })
}

@CName("k_event")
fun event(t: Int): Int {
    val c = waiting ?: return -1
    waiting = null
    c.resume(t)
    return presses
}
