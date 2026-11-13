// Language probe 10: @ThreadLocal objects, box identity, suspend functions with try/finally across suspension points,
// suspend interface members, sequences with finally, generic suspend lambdas.
import kotlin.coroutines.Continuation
import kotlin.coroutines.CoroutineContext
import kotlin.coroutines.EmptyCoroutineContext
import kotlin.coroutines.resume
import kotlin.coroutines.resumeWithException
import kotlin.coroutines.startCoroutine
import kotlin.coroutines.suspendCoroutine
import kotlin.native.concurrent.ThreadLocal

@ThreadLocal
object Session { var hits = 0; val names = mutableListOf<String>() }

@ThreadLocal
val tlsList = mutableListOf(1, 2)

interface Repo { suspend fun load(id: Int): String }

val queue = ArrayDeque<() -> Unit>()
suspend fun yieldNow() = suspendCoroutine<Unit> { c -> queue.addLast { c.resume(Unit) } }
suspend fun failLater(msg: String): Nothing = suspendCoroutine { c -> queue.addLast { c.resumeWithException(IllegalStateException(msg)) } }

class FakeRepo : Repo {
    override suspend fun load(id: Int): String { yieldNow(); if (id < 0) failLater("no id $id"); return "item$id" }
}

suspend fun <T> retry(times: Int, block: suspend () -> T): T {
    var last: Throwable? = null
    repeat(times) { attempt ->
        try { return block() } catch (e: IllegalStateException) { last = e; println("attempt $attempt failed: ${e.message}") }
    }
    throw last!!
}

suspend fun guarded(log: MutableList<String>): Int {
    try {
        log += "try"
        yieldNow()
        log += "after yield"
        failLater("boom")
    } catch (e: IllegalStateException) {
        log += "caught ${e.message}"
        yieldNow()
        return 7
    } finally {
        log += "finally"
    }
}

fun launch(name: String, block: suspend () -> Unit) {
    block.startCoroutine(object : Continuation<Unit> {
        override val context: CoroutineContext = EmptyCoroutineContext
        override fun resumeWith(result: Result<Unit>) {
            println("$name finished: ${result.exceptionOrNull()?.let { "${it::class.simpleName} ${it.message}" } ?: "ok"}")
        }
    })
}

fun runLoop() { while (queue.isNotEmpty()) queue.removeFirst()() }

fun main() {
    println("== @ThreadLocal")
    Session.hits++; Session.hits++; Session.names += "a"
    tlsList += 3
    println("${Session.hits} ${Session.names} $tlsList")

    println("== box identity")
    val a: Any = 127; val b: Any = 127
    val c: Any = 1000; val d: Any = 1000
    println("${a === b} ${c == d} ${(1 as Any) == (1L as Any)} ${(1.0 as Any) == (1.0 as Any)} ${'x' as Any === 'x' as Any}")
    val nullableInts = listOf<Int?>(1, null, 300)
    println(nullableInts.map { it?.plus(1) })

    println("== coroutines")
    val log = mutableListOf<String>()
    launch("guarded") { println("guarded -> ${guarded(log)}") }
    val repo: Repo = FakeRepo()
    launch("repo") { println(repo.load(1) + " " + repo.load(2)) }
    launch("repo-fail") { println(repo.load(-1)) }
    var calls = 0
    launch("retry") { println("retry -> " + retry(3) { calls++; if (calls < 3) failLater("try $calls") else "success on $calls" }) }
    launch("interleave") { for (i in 1..3) { print("i$i "); yieldNow() }; println() }
    runLoop()
    println(log)

    println("== sequence with finally")
    val seqLog = mutableListOf<String>()
    val s = sequence {
        try { yield(1); yield(2); yield(3) } finally { seqLog += "seq finally" }
    }
    println(s.take(2).toList() + " " + seqLog)
    println(s.toList() + " " + seqLog)
    println("done")
}
