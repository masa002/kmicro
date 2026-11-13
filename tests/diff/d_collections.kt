data class Point(val x: Int, val y: Int)
sealed interface Ev {
    data object Press : Ev
    data class Tick(val ms: Int) : Ev
    data class Text(val s: String) : Ev
}

fun describe(e: Ev): String = when (e) {
    Ev.Press -> "press"
    is Ev.Tick -> "tick ${e.ms}"
    is Ev.Text -> "text '${e.s}'"
}

fun main() {
    val xs = (1..20).toMutableList()
    xs.removeAll { it % 3 == 0 }
    println(xs)
    println(xs.map { it * it }.filter { it % 2 == 1 }.sum())
    println(xs.groupBy { it % 4 })
    println(xs.chunked(5).map { it.sum() })
    println(xs.windowed(3, 4))
    println(xs.sortedByDescending { (it * 7) % 11 })
    println(xs.fold(0L) { acc, v -> acc * 31 + v })
    val m = HashMap<String, Int>()
    for (w in "the quick brown fox jumps over the lazy dog the end".split(" ")) m[w] = (m[w] ?: 0) + 1
    println(m.toList().sortedBy { it.first })
    println(m.entries.sortedWith(compareBy({ -it.value }, { it.key })).map { "${it.key}=${it.value}" })
    val lm = linkedMapOf("z" to 1, "a" to 2, "m" to 3)
    lm["b"] = 4
    println(lm)
    val s = hashSetOf(5, 3, 9, 3, 1)
    println(s.sorted() + s.size)
    val p = Point(3, 4)
    println("$p ${p == Point(3, 4)} ${p.hashCode()} ${p.copy(y = 9)}")
    val events = listOf(Ev.Press, Ev.Tick(100), Ev.Text("hi"), Ev.Tick(2500))
    println(events.map(::describe))
    println(events.filterIsInstance<Ev.Tick>().maxByOrNull { it.ms })
    val arr = IntArray(10) { (it * 37) % 10 }
    arr.sort()
    println(arr.toList() + arr.toList().binarySearch(7))
    println(Array(3) { i -> Array(3) { j -> i * j } }.map { it.toList() })
    println(listOf(3, 1, 2).zip(listOf("c", "a", "b")).sortedBy { it.first }.unzip())
    println(generateSequence(1) { it * 3 }.takeWhile { it < 1000 }.toList())
    println((1..5).asSequence().map { it * 10 }.filter { it > 15 }.joinToString("|", "<", ">"))
}
