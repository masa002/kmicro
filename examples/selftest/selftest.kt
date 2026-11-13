// The Kotlin features a firmware leans on, one function each; main.c calls them through selftest.h and checks
// the results. Ordinary Kotlin: nothing here knows it runs on a microcontroller.
package selftest

import kotlin.coroutines.*

// ---- 1. classes, interfaces, virtual calls ----
interface Shape { fun area(): Int }
open class Rect(val w: Int, val h: Int) : Shape { override fun area() = w * h }
class Square(s: Int) : Rect(s, s)
class Tri(val b: Int, val h: Int) : Shape { override fun area() = b * h / 2 }

fun shapes(n: Int): Int {
    val all = arrayOf<Shape>(Rect(n, 2), Square(n), Tri(n, 4))
    var sum = 0
    for (s in all) sum += s.area()
    return sum
}

// ---- 2. garbage collection: 100-node garbage chains, survivors in locals, a global and an array ----
class Node(val v: Int, val next: Node?)
private var globalKeep: Node? = null

fun gcChains(rounds: Int): Int {
    var keep: Node? = null
    var sum = 0
    for (r in 0 until rounds) {
        var tmp: Node? = null
        for (i in 0 until 100) tmp = Node(i, tmp)
        keep = Node(r, keep)
        if (r % 7 == 0) globalKeep = Node(r * 1000, globalKeep)
        var t = tmp
        while (t != null) { sum += t.v; t = t.next }
    }
    var k = keep
    while (k != null) { sum += k.v; k = k.next }
    var g = globalKeep
    while (g != null) { sum += g.v; g = g.next }
    val arr = Array<Node?>(50) { Node(it, null) }
    for (n in arr) sum += n!!.v
    return sum
}

// ---- 3. strings ----
fun strings(n: Int): Int {
    var fail = 0
    val s = "battery $n mV, ok=${n > 2400}"
    if (s != "battery 2500 mV, ok=true") fail = fail or 1
    if (s.length != 24) fail = fail or 2
    if (s.hashCode() != 2137746472) fail = fail or 4
    val parts = s.split(", ")
    if (parts.size != 2 || parts[1] != "ok=true") fail = fail or 8
    if (s.replace('a', 'A').substring(0, 7) != "bAttery") fail = fail or 16
    val sb = StringBuilder()
    for (i in 1..5) sb.append(i).append(',')
    if (sb.toString() != "1,2,3,4,5,") fail = fail or 32
    val jp = "é漢字"
    if (jp.length != 3 || jp[1] != '漢') fail = fail or 64
    if (n.toString(16) != "9c4") fail = fail or 128
    if (!("abc" < "abd")) fail = fail or 256
    if ("ok=true" !in s || s.indexOf("mV") != 13) fail = fail or 512
    return fail
}

// ---- 4. exceptions: 10 checks; check k sets bit k - 1 of the result when it fails (exceptions(-3) == 0) ----
class PanelError(val code: Int) : Exception("panel error $code")
fun check(n: Int) { if (n < 0) throw PanelError(n) }
fun deep(n: Int, d: Int): Int = if (d == 0) { check(n); 1 } else deep(n, d - 1) + 1
private var fin = 0
fun withFinally(): Int { try { return 5 } finally { fin = 1 } }

fun exceptions(n: Int): Int {
    var fail = 0
    var r = 0
    try { check(n); r = 1 } catch (e: PanelError) { r = e.code } finally { r += 100 }
    if (r != n + 100) fail = fail or 1                                  // 1: caught by its type, then finally
    try { try { check(n) } catch (e: IllegalStateException) { r = 2 } } catch (e: PanelError) { r = 7 }
    if (r != 7) fail = fail or 2                                        // 2: a catch of another type is passed by
    try { deep(n, 10); r = 0 } catch (e: PanelError) { r = if (e.message == "panel error $n") 3 else -3 }
    if (r != 3) fail = fail or 4                                        // 3: ten calls deep, with its message
    try { val a = IntArray(3); a[n + 10] = 1; r = 0 } catch (e: IndexOutOfBoundsException) { r = 4 }
    if (r != 4) fail = fail or 8                                        // 4: an array index out of bounds
    try { val z = 0; r = 10 / (z * n) } catch (e: ArithmeticException) { r = 5 }
    if (r != 5) fail = fail or 16                                       // 5: a division by zero
    if (withFinally() != 5 || fin != 1) fail = fail or 32               // 6: finally after a return
    if (runCatching { check(n); 0 }.exceptionOrNull() !is PanelError) fail = fail or 64   // 7: runCatching
    r = 0
    try { require(n > 0) { "n must be positive" } } catch (e: IllegalArgumentException) {
        if (e.message == "n must be positive") r = 8
    }
    if (r != 8) fail = fail or 128                                      // 8: require, with its message
    var caught = 0
    for (i in 0 until 200) try { check(-i - 1) } catch (e: PanelError) { caught++ }
    if (caught != 200) fail = fail or 256                               // 9: 200 throws in a row
    try { IntArray(3).fill(1, 0, 10); r = 0 } catch (e: IndexOutOfBoundsException) { r = 10 }
    if (r != 10) fail = fail or 512                                     // 10: thrown through the runtime's C code
    return fail
}

fun throwOnce(n: Int): Int = try { check(n); 0 } catch (e: PanelError) { 1 }   // timed by the C side

// ---- 5. coroutines: a suspended coroutine resumed by C events ----
private var waiting: Continuation<Int>? = null
private var presses = 0
suspend fun awaitButton(): Int = suspendCoroutine { c -> waiting = c }

fun coroStart() {
    suspend { while (true) presses += awaitButton() }.startCoroutine(Continuation(EmptyCoroutineContext) { })
}

fun coroEvent(t: Int): Int {
    val c = waiting ?: return -1
    waiting = null
    c.resume(t)
    return presses
}

fun hello(): Int {
    println("Hello from Kotlin/Native 2.4.21 on a bare Cortex-M4 (no OS, kmicro runtime)")
    return 0
}
