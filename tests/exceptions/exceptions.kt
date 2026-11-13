@file:OptIn(kotlin.experimental.ExperimentalNativeApi::class)
import kotlin.native.CName

class PanelError(val code: Int) : Exception("panel error $code")

fun check(n: Int) { if (n < 0) throw PanelError(n) }
fun deep(n: Int, d: Int): Int = if (d == 0) { check(n); 1 } else deep(n, d - 1) + 1
private var fin = 0
fun withFinally(): Int { try { return 5 } finally { fin = 1 } }

@CName("k_exc")
fun exc(n: Int): Int {
    var fail = 0
    var r = 0
    try { check(n); r = 1 } catch (e: PanelError) { r = e.code } finally { r += 100 }        // 1 type + finally
    if (r != n + 100) fail = fail or 1
    try {                                                                                     // 2 no match -> outer
        try { check(n) } catch (e: IllegalStateException) { fail = fail or 2 }
    } catch (e: PanelError) { r = 7 }
    if (r != 7) fail = fail or 4
    try { deep(n, 10); fail = fail or 8 } catch (e: PanelError) {                             // 3 ten frames deep
        if (e.message != "panel error $n") fail = fail or 16
    }
    try { val a = IntArray(3); a[n + 10] = 1; fail = fail or 32 } catch (e: IndexOutOfBoundsException) { }   // 4
    try { val z = 0; val q = 10 / (z * n); if (q != 1) fail = fail or 64 } catch (e: ArithmeticException) { }
    if (withFinally() != 5 || fin != 1) fail = fail or 128                                     // 5 finally on return
    val res = runCatching { check(n); 0 }                                                     // 6 Result
    if (res.exceptionOrNull() !is PanelError) fail = fail or 256
    try { require(n > 0) { "n must be positive" } } catch (e: IllegalArgumentException) {      // 7 require
        if (e.message != "n must be positive") fail = fail or 512
    }
    var caught = 0                                                                            // 8 many throws, GC
    for (i in 0 until 200) try { check(-i - 1) } catch (e: PanelError) { caught++ }
    if (caught != 200) fail = fail or 1024
    try { IntArray(3).fill(1, 0, 10); fail = fail or 2048 } catch (e: IndexOutOfBoundsException) { }  // 9 via C
    return fail
}

@CName("k_uncaught")
fun uncaught(n: Int): Int { deep(n, 3); return 0 }
