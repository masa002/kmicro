@file:OptIn(kotlin.experimental.ExperimentalNativeApi::class)
import kotlin.native.CName

@CName("k_entry")
fun entry(n: Int): Int {
    val s = "battery $n mV, ok=${n > 2400}"
    return s.length + s.hashCode()
}
