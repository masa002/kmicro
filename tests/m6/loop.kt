@file:OptIn(kotlin.experimental.ExperimentalNativeApi::class)
package loop

import kotlin.coroutines.*
import kotlin.coroutines.intrinsics.*

// A single-thread event loop for a microcontroller. No allocation per wait: waiting continuations sit in fixed
// arrays (they are GC roots through these globals). The C main loop calls step(); when every coroutine waits,
// step() returns how long the CPU may sleep, and the C kernel sleeps (WFI here, Stop 1 on the device).
object Done : Continuation<Unit> {
    override val context: CoroutineContext get() = EmptyCoroutineContext
    override fun resumeWith(result: Result<Unit>) { result.getOrThrow() }
}

object Loop {
    private const val QN = 8
    private val ready = arrayOfNulls<Continuation<Unit>>(QN)
    private var qh = 0
    private var qn = 0
    private const val TN = 8
    private val timerAt = IntArray(TN)
    private val timerC = arrayOfNulls<Continuation<Unit>>(TN)
    private var tn = 0
    private const val EN = 4
    private val eventC = arrayOfNulls<Continuation<Unit>>(EN)
    var now = 0
        private set

    fun launch(block: suspend () -> Unit) = post(block.createCoroutineUnintercepted(Done))

    private fun post(c: Continuation<Unit>) {
        check(qn < QN) { "ready queue full" }
        ready[(qh + qn++) % QN] = c
    }

    suspend fun sleep(ms: Int): Unit = suspendCoroutineUninterceptedOrReturn { c ->
        check(tn < TN) { "too many timers" }
        timerAt[tn] = now + ms
        timerC[tn++] = c
        COROUTINE_SUSPENDED
    }

    suspend fun awaitEvent(source: Int): Unit = suspendCoroutineUninterceptedOrReturn { c ->
        eventC[source] = c
        COROUTINE_SUSPENDED
    }

    // events: one bit per source. Returns 0 = call again now, -1 = sleep until an event, else ms to the next timer.
    fun step(events: Int, nowMs: Int): Int {
        now = nowMs
        var ev = events
        while (ev != 0) {
            val s = ev.countTrailingZeroBits()
            ev = ev and (ev - 1)
            val c = eventC[s]
            if (c != null) { eventC[s] = null; post(c) }
        }
        var i = 0
        while (i < tn) {
            if (timerAt[i] - now <= 0) {
                post(timerC[i]!!)
                tn--
                timerAt[i] = timerAt[tn]; timerC[i] = timerC[tn]; timerC[tn] = null
            } else i++
        }
        var budget = 8
        while (qn > 0 && budget-- > 0) {
            val c = ready[qh]!!
            ready[qh] = null
            qh = (qh + 1) % QN
            qn--
            c.resume(Unit)
        }
        if (qn > 0) return 0
        if (tn == 0) return -1
        var next = Int.MAX_VALUE
        for (j in 0 until tn) next = minOf(next, timerAt[j] - now)
        return maxOf(next, 1)
    }
}

const val BUTTON = 0
var ticks = 0
var presses = 0
var lastPressAt = -1

fun startApp() {
    Loop.launch {                                   // a periodic job
        while (true) {
            Loop.sleep(500)
            ticks++
            println("[${Loop.now} ms] tick $ticks")
        }
    }
    Loop.launch {                                   // the button, with a 50 ms debounce pause after each press
        while (true) {
            Loop.awaitEvent(BUTTON)
            presses++
            lastPressAt = Loop.now
            println("[${Loop.now} ms] button pressed ($presses)")
            Loop.sleep(50)
        }
    }
}

fun step(events: Int, nowMs: Int): Int = Loop.step(events, nowMs)
fun result(): Int = ticks * 100 + presses
