@file:OptIn(kotlin.experimental.ExperimentalNativeApi::class)
import kotlin.native.CName

class PanelError(val code: Int) : Exception()

fun check(n: Int) { if (n < 0) throw PanelError(n) }

@CName("k_entry")
fun entry(n: Int): Int {
    var r = 0
    try { check(n); r = 1 } catch (e: PanelError) { r = e.code } finally { r += 100 }
    return r
}
