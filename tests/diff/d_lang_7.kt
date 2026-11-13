// Language probe 7: things a Kotlin developer tries next: coroutines builders, use/Result, atomics,
// exception chaining, arrays, Duration, hashCode/toString of common types. (kotlin.random and the clock:
// d_known_random_time.kt)
// difftest: large -- one program with all of the above: about 263 KB of flash
import kotlin.coroutines.Continuation
import kotlin.coroutines.EmptyCoroutineContext
import kotlin.coroutines.createCoroutine
import kotlin.coroutines.resume
import kotlin.coroutines.startCoroutine
import kotlin.coroutines.suspendCoroutine
import kotlin.time.Duration.Companion.milliseconds
import kotlin.time.Duration.Companion.seconds

class Res(val name: String, val log: MutableList<String>) : AutoCloseable {
    override fun close() { log += "close $name" }
}

var pending: Continuation<Int>? = null
suspend fun waitValue(): Int = suspendCoroutine { pending = it }

suspend fun twoSteps(log: MutableList<String>): String {
    log += "start"
    val a = waitValue()
    log += "got $a"
    val b = waitValue()
    log += "got $b"
    return "sum=${a + b}"
}

class AppError(msg: String, cause: Throwable? = null) : Exception(msg, cause)

fun describe(e: Throwable?) = "${e?.let { it::class.simpleName }}: ${e?.message}"

@kotlin.concurrent.Volatile var flag = 0

fun main() {
    println("== sequence / iterator builders")
    val fib = sequence {
        var a = 0; var b = 1
        while (true) { yield(a); val t = a + b; a = b; b = t }
    }
    println(fib.take(10).toList())
    val it = iterator { yield(1); yieldAll(listOf(2, 3)); yield(4) }
    val got = mutableListOf<Int>(); while (it.hasNext()) got += it.next()
    println(got)
    println(generateSequence(1) { if (it < 50) it * 3 else null }.toList())

    println("== suspend + continuations")
    val log = mutableListOf<String>()
    var result: Result<String>? = null
    val body: suspend () -> String = { twoSteps(log) }
    body.startCoroutine(Continuation(EmptyCoroutineContext) { result = it })
    pending!!.resume(3)
    pending!!.resume(4)
    println("$log $result")
    val c = suspend { 41 + 1 }.createCoroutine(Continuation(EmptyCoroutineContext) { r -> println("completed $r") })
    c.resume(Unit)
    val failing: suspend () -> Int = { throw AppError("in coroutine") }
    failing.startCoroutine(Continuation(EmptyCoroutineContext) { r -> println("failed: ${describe(r.exceptionOrNull())}") })

    println("== use / Result / exceptions")
    val ulog = mutableListOf<String>()
    Res("a", ulog).use { r -> ulog += "using ${r.name}" }
    runCatching { Res("b", ulog).use { throw IllegalStateException("inside use") } }.onFailure { ulog += describe(it) }
    println(ulog)
    val ok = runCatching { "42".toInt() }
    val bad = runCatching { "x".toInt() }
    println("${ok.isSuccess} ${ok.getOrNull()} ${bad.isFailure} ${bad.getOrDefault(-1)} ${bad.exceptionOrNull()?.message}")
    println(ok.map { it * 2 }.getOrThrow())
    println(bad.recover { 0 }.getOrThrow())
    println(Result.success(1))
    println(Result.failure<Int>(AppError("f")).toString())
    val wrapped = runCatching { try { error("low") } catch (e: Exception) { throw AppError("high", e) } }.exceptionOrNull()
    println("${describe(wrapped)} cause=${describe(wrapped?.cause)}")
    println(wrapped.toString())
    println(AppError("text").toString())
    println(RuntimeException().toString() + " | " + RuntimeException(null as String?).message)
    val sup = Exception("main")
    sup.addSuppressed(Exception("extra"))
    println(sup.suppressedExceptions.map { it.message })
    val trace = AppError("t").stackTraceToString().lineSequence().first()
    println(trace)
    var fin = ""
    fun nested(): Int { try { try { throw AppError("inner") } finally { fin += "f1 " } } catch (e: AppError) { fin += "c " ; return 1 } finally { fin += "f2" } }
    println("${nested()} $fin")

    println("== atomics / volatile")
    val ai = kotlin.concurrent.AtomicInt(5)
    ai.incrementAndGet(); ai.addAndGet(10)
    println("${ai.value} ${ai.compareAndSet(16, 1)} ${ai.value} ${ai.getAndSet(7)} ${ai.value}")
    val al = kotlin.concurrent.AtomicLong(1L shl 40)
    al.incrementAndGet()
    println(al.value)
    val ar = kotlin.concurrent.AtomicReference("a")
    println("${ar.compareAndSet("a", "b")} ${ar.value}")
    flag = 3; flag++
    println(flag)

    println("== arrays")
    val grid = Array(3) { r -> IntArray(3) { c2 -> r * 3 + c2 } }
    println(grid.joinToString(" | ") { it.joinToString(",") })
    println(grid.contentDeepToString())
    println(arrayOf(1, 2).contentToString() + intArrayOf(3, 4).contentToString() + charArrayOf('a', 'b').concatToString())
    println("${intArrayOf(1, 2).contentEquals(intArrayOf(1, 2))} ${arrayOf("a").contentHashCode() == arrayOf("a").contentHashCode()}")
    val arr2 = arrayOfNulls<String>(2); arr2[1] = "z"
    println(arr2.toList())
    val (a0, a1) = intArrayOf(7, 8)
    println("$a0 $a1")
    println(booleanArrayOf(true, false).toList() + byteArrayOf(1, -1).toList() + longArrayOf(1L).toList() + doubleArrayOf(0.5).toList())
    println(UIntArray(2) { (it + 1).toUInt() }.toList())

    println("== hashCode / toString of common types")
    println("${"abc".hashCode()} ${42.hashCode()} ${42L.hashCode()} ${(1L shl 40).hashCode()} ${true.hashCode()} ${'a'.hashCode()} ${1.5.hashCode()} ${1.5f.hashCode()}")
    println("${listOf(1, 2).hashCode()} ${setOf("a").hashCode()} ${mapOf(1 to "a").hashCode()} ${Pair(1, 2).hashCode()}")
    println("${null.hashCode()} ${null.toString()} ${Unit.hashCode() == Unit.hashCode()} $Unit ${(1 to "x")}")

    println("== Duration")
    println("${1500.milliseconds} ${2.seconds + 250.milliseconds} ${90.seconds.inWholeMinutes}")
    println("done")
}
