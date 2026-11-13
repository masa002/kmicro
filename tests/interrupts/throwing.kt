package isr

// A handler that throws and catches while the thread code is itself between a throw and its catch. The handler's
// exception exists before interrupts are enabled (kt_init_all creates the object), so throwing it allocates nothing.
// The runtime keeps one exception record per running context: both exceptions reach their own catch.

object Busy : RuntimeException("busy")

fun busy(): Nothing = throw Busy

fun fail(n: Int): Nothing = throw IllegalStateException("round $n")

// What SysTick_Handler calls.
fun throwInHandler(): Int = try {
    busy()
} catch (e: RuntimeException) {
    if (e === Busy) 1 else 0
}

// The thread code: n new exceptions, thrown from a called function and caught here. Returns the number caught with
// the right message.
fun throwInThread(n: Int): Int {
    var caught = 0
    repeat(n) {
        try {
            fail(it)
        } catch (e: IllegalStateException) {
            if (e.message == "round $it") caught++
        }
    }
    return caught
}
