package isr

// A handler may move references while the collector marks: SysTick swaps two fields of each Holder (or the two ends
// of an array) thousands of times while the main code allocates, which under KM_GC_STRESS collects before every
// allocation. The collector must still find both boxes every time; a box it freed is overwritten (0xA5 under stress,
// or reused by a junk Box), which the checks see as a wrong value.

class Box(val value: Int)

class Holder(var a: Box?) {
    // padding: marking a Holder takes long enough for the swap to land in between
    var p0: Any? = null; var p1: Any? = null; var p2: Any? = null; var p3: Any? = null; var p4: Any? = null
    var p5: Any? = null; var p6: Any? = null; var p7: Any? = null; var p8: Any? = null; var p9: Any? = null
    var p10: Any? = null; var p11: Any? = null; var p12: Any? = null; var p13: Any? = null; var p14: Any? = null
    var p15: Any? = null; var p16: Any? = null; var p17: Any? = null; var p18: Any? = null; var p19: Any? = null
    var p20: Any? = null; var p21: Any? = null; var p22: Any? = null; var p23: Any? = null
    var b: Box? = null
}

val holders = Array(32) { Holder(Box(1000001)).also { h -> h.b = Box(1000002) } }
val slots = Array<Box?>(1024) { null }.also { it[0] = Box(2000001); it[1023] = Box(2000002) }

fun swapSetup(): Int = holders.size + slots.size

// in the handler
fun swapFields(): Int {
    for (h in holders) {
        val t = h.a
        h.a = h.b
        h.b = t
    }
    return holders.size
}

fun swapSlots(): Int {
    val t = slots[0]
    slots[0] = slots[1023]
    slots[1023] = t
    return slots.size
}

// in main
fun checkFields(rounds: Int): Int {
    var bad = 0
    repeat(rounds) {
        val junk = Array(4) { Box(it) }
        for (h in holders)
            if (!ok(h.a, 1000001) || !ok(h.b, 1000001) || junk.size != 4) bad++
    }
    return bad
}

fun checkSlots(rounds: Int): Int {
    var bad = 0
    repeat(rounds) {
        val junk = Array(4) { Box(it) }
        if (!slotsOk() || junk.size != 4) bad++
    }
    return bad
}

// A live box holds one of its two values. (A swap between two reads may show the same box twice, which is fine.)
fun ok(x: Box?, base: Int): Boolean = x != null && (x.value == base || x.value == base + 1)

// its own function, so that the caller's frame does not keep the two boxes alive
fun slotsOk(): Boolean = ok(slots[0], 2000001) && ok(slots[1023], 2000001)
