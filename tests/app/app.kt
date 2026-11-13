@file:OptIn(kotlin.experimental.ExperimentalNativeApi::class)
import kotlin.coroutines.*
import kotlin.native.CName

// A slice of a typical device app: events from C, a small state machine, a log of strings.
sealed interface Ev { object Press : Ev; object Dock : Ev; data class Tick(val ms: Int) : Ev }

class Device {
    var docked = false
    val log = ArrayList<String>()
    fun on(e: Ev): Int = when (e) {
        Ev.Press -> { log.add("press docked=$docked"); if (docked) 2 else 1 }
        Ev.Dock -> { docked = !docked; log.add("dock $docked"); 3 }
        is Ev.Tick -> if (e.ms > 1000) 4 else 0
    }
}

private val dev = Device()
private var waiting: Continuation<Ev>? = null
private var last = 0
suspend fun next(): Ev = suspendCoroutine { waiting = it }

@CName("k_start")
fun start() {
    suspend { while (true) { last = dev.on(next()) } }.startCoroutine(Continuation(EmptyCoroutineContext) { })
}

@CName("k_event")
fun event(kind: Int, arg: Int): Int {
    val e = when (kind) { 0 -> Ev.Press; 1 -> Ev.Dock; else -> Ev.Tick(arg) }
    val c = waiting ?: return -1
    waiting = null
    c.resume(e)
    return last * 1000 + dev.log.size
}
