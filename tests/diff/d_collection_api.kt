// Collections API: lists, sets, maps, ArrayDeque, transformations, sorting, equality, the exceptions and their messages.
// difftest: heap 49152 -- main keeps every collection of the test alive until it returns, and the free memory
// ends up in small pieces: 40 KB runs out
// difftest: large -- most of the collections API in one program: about 350 KB of flash

data class P(val name: String, val age: Int)

fun err(label: String, block: () -> Any?) {
    val r = runCatching(block)
    val e = r.exceptionOrNull()
    println("$label: " + if (e == null) "ok ${r.getOrNull()}" else "${e::class.simpleName}: ${e.message}")
}

fun main() {
    // --- List / MutableList / ArrayList
    val l = mutableListOf(5, 3, 8, 1)
    l.add(9); l.add(0, 7); l.remove(8); l.removeAt(1)
    println("list ops: $l size=${l.size}")
    println("subList: ${l.subList(1, 3)} indexOf=${l.indexOf(9)} lastIndexOf=${l.lastIndexOf(42)} contains=${1 in l}")
    l.sort(); println("sort: $l"); l.sortDescending(); println("sortDescending: $l"); l.reverse(); println("reverse: $l")
    l[0] = 100; l.addAll(1, listOf(-1, -2)); println("set/addAll: $l")
    l.removeAll { it < 0 }; l.retainAll(listOf(100, 1, 7, 9)); println("removeAll/retainAll: $l")
    println("removeFirst=${l.removeFirst()} removeLast=${l.removeLast()} -> $l")
    val al = ArrayList<String>(2); al.add("x"); al.add("y"); al.add("z"); al.ensureCapacity(50); al.trimToSize()
    println("ArrayList: $al ${al.joinToString("")} asReversed=${al.asReversed()}")
    // --- sets
    val hs = HashSet<String>(); hs.addAll(listOf("pear", "apple", "fig", "apple", "kiwi", "plum"))
    println("HashSet iter: $hs size=${hs.size} fig=${"fig" in hs}")
    val lhs = linkedSetOf(3, 1, 2, 3); lhs.remove(1); lhs.add(1); println("LinkedHashSet: $lhs")
    val ms = mutableSetOf("b", "a"); ms += "c"; ms -= "b"; println("mutableSetOf: $ms")
    println("setOf(data): ${setOf(P("a", 1), P("a", 1), P("b", 2))}")
    // --- maps
    val hm = HashMap<String, Int>()
    for (w in "a b c a b a dd eee".split(" ")) hm[w] = hm.getOrPut(w) { 0 } + 1
    println("HashMap: $hm")
    val im = HashMap<Int, String>(); for (i in listOf(100, -3, 17, 64, 1 shl 20, 5)) im[i] = "v$i"; println("HashMap<Int>: $im")
    val lm = linkedMapOf("x" to 1, "y" to 2, "z" to 3, "w" to 4)
    println("mapValues: ${lm.mapValues { it.value * 10 }} mapKeys: ${lm.mapKeys { it.key.uppercase() }} filterKeys: ${lm.filterKeys { it != "y" }} filterValues: ${lm.filterValues { it > 2 }}")
    println("entries: ${lm.entries.joinToString { "${it.key}->${it.value}" }} keys=${lm.keys} values=${lm.values}")
    val iter = lm.entries.iterator(); while (iter.hasNext()) if (iter.next().value % 2 == 0) iter.remove()
    println("after iterator.remove: $lm")
    lm.getOrPut("q") { 7 }; lm["x"] = lm.getValue("x") + 5; lm.put("z", 6); println("getOrPut/put: $lm put-return=${lm.put("q", 8)} remove-return=${lm.remove("nope")}")
    println("getOrElse=${lm.getOrElse("none") { -2 }} withDefault=${lm.withDefault { it.length }.getValue("abcd")}")
    err("getValue missing") { lm.getValue("missing") }
    println("toSortedMap-like: ${lm.toList().sortedBy { it.first }.toMap()} maxBy=${lm.maxByOrNull { it.value }?.key}")
    val em = mutableMapOf<String, MutableList<Int>>(); em.getOrPut("k") { mutableListOf() }.add(1); em.getOrPut("k") { mutableListOf() }.add(2); println("getOrPut list: $em")
    // --- ArrayDeque
    val dq = ArrayDeque<Int>(); dq.addLast(1); dq.addLast(2); dq.addFirst(0); dq.addFirst(-1)
    println("ArrayDeque: $dq first=${dq.first()} last=${dq.last()} removeFirst=${dq.removeFirst()} removeLast=${dq.removeLast()} -> $dq")
    for (i in 0 until 20) dq.addLast(i); repeat(15) { dq.removeFirst() }; println("ArrayDeque wrap: $dq ${dq.size}")
    err("ArrayDeque empty") { ArrayDeque<Int>().removeFirst() }
    // --- functional ops
    val xs = listOf(4, 8, 15, 16, 23, 42)
    println("map/filter/flatMap: ${xs.map { it / 2 }} ${xs.filter { it % 2 == 0 }} ${xs.flatMap { listOf(it, -it) }.take(5)}")
    println("groupBy: ${xs.groupBy { it % 3 }} groupingBy: ${xs.groupingBy { it % 3 }.eachCount()}")
    println("associate: ${xs.associate { it to it * it }} associateBy: ${xs.associateBy { it % 5 }} associateWith: ${xs.associateWith { "n$it" }}")
    println("partition: ${xs.partition { it > 15 }} chunked: ${xs.chunked(4)} windowed: ${xs.windowed(3, 2, partialWindows = true)}")
    println("zip: ${xs.zip(listOf("a", "b", "c"))} unzip: ${listOf(1 to "a", 2 to "b").unzip()} zipWithNext: ${xs.zipWithNext { a, b -> b - a }}")
    println("fold=${xs.fold(1L) { a, v -> a * v }} reduce=${xs.reduce { a, v -> a - v }} scan=${xs.scan(0) { a, v -> a + v }} runningFold=${xs.runningFold(10) { a, v -> a - v }} runningReduce=${xs.runningReduce { a, b -> a * b % 97 }}")
    println("sumOf=${xs.sumOf { it.toLong() * 3 }} sumOfD=${xs.sumOf { it / 3.0 }} average=${xs.average()} min=${xs.minOrNull()} max=${xs.maxOrNull()} minBy=${xs.minByOrNull { -it }} maxBy=${xs.maxByOrNull { it % 7 }} emptyMax=${emptyList<Int>().maxOrNull()}")
    val people = listOf(P("Ann", 31), P("bob", 25), P("Cid", 31), P("dee", 25), P("Eve", 40))
    println("sortedBy: ${people.sortedBy { it.age }.map { it.name }}")
    println("sortedWith thenByDescending: ${people.sortedWith(compareBy<P> { it.age }.thenByDescending { it.name }).map { it.name }}")
    println("sortedWith thenBy CI: ${people.sortedWith(compareByDescending<P> { it.age }.thenBy(String.CASE_INSENSITIVE_ORDER) { it.name }).map { it.name }}")
    println("distinctBy: ${people.distinctBy { it.age }.map { it.name }} distinct: ${listOf(1, 2, 1, 3, 2).distinct()}")
    println("take/drop: ${xs.take(2)} ${xs.drop(4)} ${xs.takeLast(2)} ${xs.dropLast(5)} takeWhile=${xs.takeWhile { it < 16 }} dropWhile=${xs.dropWhile { it < 16 }}")
    println("first=${xs.first()} last=${xs.last()} firstOrNull=${xs.firstOrNull { it > 100 }} single=${listOf(7).single()} find=${xs.find { it > 10 }} findLast=${xs.findLast { it < 20 }}")
    println("any=${xs.any { it > 40 }} all=${xs.all { it > 3 }} none=${xs.none { it == 0 }} count=${xs.count { it % 2 == 1 }}")
    println("withIndex: ${xs.withIndex().filter { it.index % 2 == 0 }.map { "${it.index}:${it.value}" }}")
    val sb = StringBuilder(); xs.forEachIndexed { i, v -> sb.append(i * v).append(',') }; println("forEachIndexed: $sb")
    println("joinToString: ${xs.joinToString(separator = "; ", prefix = "<", postfix = ">", limit = 3, truncated = "...") { "#$it" }}")
    println("binarySearch: ${xs.binarySearch(16)} ${xs.binarySearch(5)} ${people.map { it.name }.sorted().binarySearch("Cid")} ${xs.binarySearchBy(23) { it }}")
    println("buildList: ${buildList { add(1); addAll(listOf(2, 3)); add(0, 0) }} buildMap: ${buildMap { put("a", 1); put("b", 2) }} buildSet: ${buildSet { add(3); add(1); add(3) }}")
    val arr: Array<Int> = xs.toTypedArray(); println("toTypedArray: ${arr.size} ${arr.contentToString()}")
    println("plus/minus: ${xs + 99} ${xs - 15} ${xs + listOf(1, 2)} ${xs - setOf(4, 42)} ${setOf(1, 2) + 3} ${mapOf(1 to 2) + (3 to 4)} ${mapOf(1 to 2, 3 to 4) - 1}")
    println("intersect/union/subtract: ${xs intersect setOf(15, 16, 99)} ${listOf(1, 2) union listOf(2, 3)} ${xs subtract setOf(4, 8)}")
    println("flatten: ${listOf(listOf(1), listOf(2, 3)).flatten()} sumOf: ${listOf(1.5, 2.25).sum()} mapNotNull: ${listOf("1", "x", "3").mapNotNull { it.toIntOrNull() }} filterNotNull: ${listOf(1, null, 2).filterNotNull()}")
    println("ranges: ${(1..10 step 3).toList()} ${(10 downTo 1 step 4).toList()} ${(0 until 3).toList()} ${(0..<3).reversed()} ${('a'..'e').joinToString("")} ${(1L..3L).sum()} ${(5..1).isEmpty()}")
    println("fill: ${MutableList(3) { 0 }.apply { fill(7) }}")
    println("sortedDescending/reversed: ${xs.sortedDescending()} ${xs.reversed()} ${xs.sortedByDescending { it % 10 }} ${listOf("b", "A", "c").sortedWith(String.CASE_INSENSITIVE_ORDER)}")
    // --- equality and toString of nested collections
    val nested = listOf(listOf(1, 2), setOf("a"), mapOf(1 to listOf(3, 4)), emptyList<Int>(), arrayListOf(null))
    println("nested: $nested eq=${nested == listOf(listOf(1, 2), setOf("a"), mapOf(1 to listOf(3, 4)), listOf<Int>(), listOf(null))}")
    println("list==mutable: ${listOf(1, 2) == mutableListOf(1, 2)} set eq: ${setOf(1, 2) == hashSetOf(2, 1)} map eq: ${mapOf("a" to 1, "b" to 2) == linkedMapOf("b" to 2, "a" to 1)}")
    val selfRef = mutableListOf<Any>(1); selfRef.add(selfRef); println("selfRef: $selfRef")
    // --- exceptions
    err("first empty") { emptyList<Int>().first() }
    err("single many") { listOf(1, 2).single() }
    err("get oob") { listOf(1, 2, 3)[5] }
    err("mutable get oob") { mutableListOf(1, 2, 3)[-1] }
    err("reduce empty") { emptyList<Int>().reduce { a, b -> a + b } }
    err("subList bad") { listOf(1, 2, 3).subList(2, 1) }
    err("listOf add") { (listOf(1, 2) as MutableList<Int>).add(3) }
    err("CME") { val m = mutableListOf(1, 2, 3, 4); for (v in m) if (v == 2) m.remove(v); m }
    err("CME map") { val m = hashMapOf(1 to 1, 2 to 2, 3 to 3); for (k in m.keys) if (k == 1) m[10] = 10; m }
    err("iterator remove twice") { val it = mutableListOf(1, 2).iterator(); it.next(); it.remove(); it.remove() }
    err("ArrayList(-1)") { ArrayList<Int>(-1) }
    err("chunked 0") { xs.chunked(0) }
    println("done")
}
