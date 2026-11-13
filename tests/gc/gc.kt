@file:OptIn(kotlin.experimental.ExperimentalNativeApi::class)
import kotlin.native.CName

class Node(val v: Int, val next: Node?)

// Survivors live in a global and in a local chain; garbage is a 100-node chain per round.
private var globalKeep: Node? = null

@CName("k_gc")
fun gc(rounds: Int): Int {
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
    val arr = Array<Node?>(50) { Node(it, null) }   // an object array: elements are roots through the array
    for (n in arr) sum += n!!.v
    return sum
}
