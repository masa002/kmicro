@file:OptIn(kotlin.experimental.ExperimentalNativeApi::class, ExperimentalUnsignedTypes::class)

// ByteArray.get/set{Char,Short,Int,Long,Float,Double}At: little-endian values at any byte index, and the bounds.

fun hex(b: ByteArray) = b.joinToString("") { (it.toInt() and 0xFF).toString(16).padStart(2, '0') }

fun bounds(label: String, block: () -> Any) =
    println("$label: " + try { block().toString() } catch (e: IndexOutOfBoundsException) { e::class.simpleName!! })

fun main() {
    val b = ByteArray(17) { (it * 37 + 5).toByte() }
    for (i in 0..9)
        println("get $i: ${b.getCharAt(i).code} ${b.getShortAt(i)} ${b.getUShortAt(i)} ${b.getIntAt(i)} ${b.getUIntAt(i)} " +
            "${b.getLongAt(i)} ${b.getULongAt(i)} ${b.getFloatAt(i).toBits()} ${b.getDoubleAt(i).toBits()}")
    val w = ByteArray(16)
    w.setCharAt(1, '\uABCD'); println("setCharAt 1: ${hex(w)}")
    w.setShortAt(3, -2); println("setShortAt 3: ${hex(w)}")
    w.setUShortAt(5, 0xBEEFu); println("setUShortAt 5: ${hex(w)}")
    w.fill(0); w.setIntAt(1, 0x12345678); println("setIntAt 1: ${hex(w)}")
    w.setUIntAt(7, 0xCAFEBABEu); println("setUIntAt 7: ${hex(w)}")
    w.fill(0); w.setLongAt(3, -0x123456789ABCDEFL); println("setLongAt 3: ${hex(w)}")
    w.setULongAt(8, ULong.MAX_VALUE - 1u); println("setULongAt 8: ${hex(w)}")
    w.fill(0); w.setFloatAt(5, -1.5f); println("setFloatAt 5: ${hex(w)} ${w.getFloatAt(5)}")
    w.setDoubleAt(7, 3.141592653589793); println("setDoubleAt 7: ${hex(w)} ${w.getDoubleAt(7)}")
    w.setUByteAt(0, 0xFFu); println("setUByteAt 0: ${hex(w)} ${w.getUByteAt(0)}")
    for (width in listOf(2, 4, 8)) {
        val last = w.size - width
        val get: (Int) -> Any = when (width) { 2 -> { i -> w.getShortAt(i) }; 4 -> { i -> w.getIntAt(i) }; else -> { i -> w.getLongAt(i) } }
        for (i in listOf(last, last + 1, -1, Int.MIN_VALUE, Int.MAX_VALUE)) bounds("get$width $i", { get(i) })
    }
    bounds("getCharAt 15", { w.getCharAt(15) })
    bounds("getFloatAt 13", { w.getFloatAt(13) })
    bounds("getDoubleAt 9", { w.getDoubleAt(9) })
    bounds("setIntAt 13", { w.setIntAt(13, 1) })
    bounds("setLongAt -1", { w.setLongAt(-1, 1) })
    bounds("setDoubleAt 8", { w.setDoubleAt(8, 2.0); w.getDoubleAt(8) })
    bounds("setShortAt 15", { w.setShortAt(15, 1) })
    bounds("empty getShortAt 0", { ByteArray(0).getShortAt(0) })
    bounds("one getShortAt 0", { ByteArray(1).getShortAt(0) })
    println("after: ${hex(w)}")
}
