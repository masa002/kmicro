// Arrays of every primitive type, Array<T>, unsigned arrays, sequences.
// difftest: heap 32768 -- main keeps every array and sequence of the test alive until it returns
// difftest: large -- the API of every array type in one program: about 310 KB of flash
fun err(label: String, block: () -> Any?) {
    val r = runCatching(block)
    val e = r.exceptionOrNull()
    println("$label: " + if (e == null) "ok ${r.getOrNull()}" else "${e::class.simpleName}: ${e.message}")
}

@OptIn(ExperimentalUnsignedTypes::class)
fun main() {
    // --- arrays
    val ia = IntArray(6) { (it * 7) % 5 - 2 }
    println("IntArray: ${ia.contentToString()} copyOf=${ia.copyOf(8).contentToString()} copyOfShort=${ia.copyOf(2).contentToString()} range=${ia.copyOfRange(1, 4).contentToString()}")
    ia.fill(9, 1, 3); println("fill: ${ia.contentToString()}"); ia.sort(); println("sort: ${ia.contentToString()} sortedArrayDesc=${ia.sortedArrayDescending().contentToString()}")
    ia.reverse(); println("reverse: ${ia.contentToString()} sum=${ia.sum()} avg=${ia.average()} max=${ia.max()} min=${ia.minOrNull()} indices=${ia.indices} lastIndex=${ia.lastIndex}")
    println("contentEquals=${ia.contentEquals(ia.copyOf())} ${ia.contentEquals(IntArray(6))} contentHashCode=${ia.contentHashCode()} ${intArrayOf().contentHashCode()}")
    val la = LongArray(4) { Long.MAX_VALUE - it }; println("LongArray: ${la.contentToString()} ${la.contentHashCode()}")
    val da = doubleArrayOf(0.1, -0.0, 1e300, Double.NaN, 2.5); println("DoubleArray: ${da.contentToString()} ${da.contentHashCode()} sorted=${da.sortedArray().contentToString()}")
    val fa = floatArrayOf(1.1f, -2f, Float.POSITIVE_INFINITY); println("FloatArray: ${fa.contentToString()} ${fa.contentHashCode()}")
    val ba = BooleanArray(3) { it == 1 }; println("BooleanArray: ${ba.contentToString()} ${ba.contentHashCode()}")
    val ca = charArrayOf('k', 'o', 't', 'é', "😀"[0]); println("CharArray: ${ca.contentToString()} concat=${ca.concatToString(0, 4)} ${ca.contentHashCode()}")
    val by = byteArrayOf(-128, 0, 127, 0x7f, -1); println("ByteArray: ${by.contentToString()} ${by.contentHashCode()} sorted=${by.sorted()}")
    val sa = ShortArray(3) { (it * 20000).toShort() }; println("ShortArray: ${sa.contentToString()} ${sa.contentHashCode()}")
    val arr = Array(4) { "s$it" }; println("Array<String>: ${arr.contentToString()} ${arr.contentHashCode()} ${arr.joinToString("")}")
    val nulls = arrayOfNulls<String>(3); nulls[1] = "mid"; println("arrayOfNulls: ${nulls.contentToString()} ${nulls.filterNotNull()}")
    val grid = Array(3) { r -> IntArray(4) { c -> r * 4 + c } }
    grid[2][3] = -1; println("2D: ${grid.joinToString { it.contentToString() }} deep=${arrayOf(intArrayOf(1, 2), arrayOf("a", arrayOf(3)), null).contentDeepToString()}")
    println("deepEquals=${arrayOf(intArrayOf(1), arrayOf("x")).contentDeepEquals(arrayOf(intArrayOf(1), arrayOf("x")))} deepHash=${arrayOf(intArrayOf(1, 2), arrayOf("x")).contentDeepHashCode()}")
    val words = arrayOf("pear", "Fig", "apple", "kiwi"); words.sort(); println("Array sort: ${words.contentToString()}")
    words.sortWith(compareBy { it.length }); println("sortWith: ${words.contentToString()}"); words.sortBy { it.last() }; println("sortBy: ${words.contentToString()}")
    words.sortDescending(); println("sortDescending: ${words.contentToString()}")
    val dst = IntArray(8); intArrayOf(1, 2, 3, 4).copyInto(dst, 2, 1, 3); println("copyInto: ${dst.contentToString()}")
    val ov = intArrayOf(1, 2, 3, 4, 5); ov.copyInto(ov, 1, 0, 4); println("copyInto overlap: ${ov.contentToString()}")
    println("asList: ${ov.asList()} toList=${ov.toList().subList(1, 3)} toSet=${ov.toSet()} toMutableList=${ov.toMutableList()} reversedArray=${ov.reversedArray().contentToString()}")
    println("array map/filter: ${ov.map { it * 2 }} ${ov.filter { it > 2 }} ${ov.indexOf(3)} ${ov.count { it == 1 }} ${ov.withIndex().last()}")
    val ua = uintArrayOf(1u, UInt.MAX_VALUE, 0x80000000u); println("UIntArray: ${ua.contentToString()} ${ua.sum()} ${ua.sorted()} ${ua.maxOrNull()}")
    val uba = ubyteArrayOf(255u, 1u); println("UByteArray: ${uba.contentToString()} ${uba.toByteArray().contentToString()}")
    err("IntArray oob") { IntArray(3)[5] }
    err("Array oob") { arrayOf("a")[-1] }
    err("copyOfRange bad") { intArrayOf(1, 2).copyOfRange(1, 5) }
    err("fill bad") { IntArray(3).fill(1, 2, 5) }
    err("negative size") { IntArray(-1) }
    err("copyInto bad") { intArrayOf(1, 2).copyInto(IntArray(1)) }
    err("max empty") { intArrayOf().max() }
    // --- sequences
    println("generateSequence: ${generateSequence(1) { if (it < 200) it * 3 else null }.toList()}")
    var n = 0
    println("generateSequence {}: ${generateSequence { if (n < 5) n++ else null }.toList()}")
    val log = StringBuilder()
    val lazy = listOf(1, 2, 3, 4, 5).asSequence().map { log.append("m$it "); it * 10 }.filter { log.append("f$it "); it > 15 }.take(2)
    log.append("| built | "); val r = lazy.toList(); println("laziness: $r order: $log")
    val seq = sequence { yield(1); yieldAll(listOf(2, 3)); yieldAll(generateSequence(10) { it + 10 }.take(3)); yield(99) }
    println("sequence{}: ${seq.toList()} again=${seq.count()}")
    val it2 = iterator { yield("a"); yieldAll(listOf("b", "c")) }; val got = mutableListOf<String>(); it2.forEach { got.add(it) }; println("iterator{}: $got")
    println("infinite take: ${generateSequence(0L) { it + 7 }.filter { it % 3 == 0L }.take(5).toList()} ${sequence { var i = 0; while (true) yield(i++) }.drop(5).take(3).toList()}")
    val once = sequenceOf(1, 2, 3).constrainOnce(); println("constrainOnce first: ${once.toList()}")
    err("constrainOnce second") { once.toList() }
    println("seq ops: ${(1..10).asSequence().chunked(3).toList()} ${(1..6).asSequence().windowed(2, 3).toList()} ${sequenceOf(3, 1, 3, 2).distinct().sorted().toList()} ${sequenceOf("a", "bb").flatMap { it.asSequence() }.toList()}")
    println("seq zip: ${sequenceOf(1, 2, 3).zip(sequenceOf("x", "y")).toList()} zipWithNext=${sequenceOf(1, 4, 9).zipWithNext().toList()} withIndex=${sequenceOf("p", "q").withIndex().toList()}")
    println("seq agg: ${(1..5).asSequence().sum()} ${(1..5).asSequence().fold("") { a, b -> a + b }} ${(1..5).asSequence().maxOrNull()} ${sequenceOf(2, 4).all { it % 2 == 0 }} ${emptySequence<Int>().firstOrNull()} ${(1..4).asSequence().joinToString("-")}")
    println("seq runningFold: ${(1..4).asSequence().runningFold(0) { a, b -> a + b }.toList()} scan=${sequenceOf(1, 2).scan("s") { a, b -> a + b }.toList()} plus=${(sequenceOf(1) + sequenceOf(2, 3)).toList()} ifEmpty=${emptySequence<Int>().ifEmpty { sequenceOf(-1) }.toList()}")
    err("seq first empty") { emptySequence<Int>().first() }
    println("done")
}
