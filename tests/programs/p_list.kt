@file:OptIn(kotlin.experimental.ExperimentalNativeApi::class)
import kotlin.native.CName

@CName("k_entry")
fun entry(n: Int): Int {
    val xs = mutableListOf<Int>()
    for (i in 0 until n) xs.add(i * i)
    return xs.filter { it % 2 == 0 }.map { it + 1 }.sum()
}
