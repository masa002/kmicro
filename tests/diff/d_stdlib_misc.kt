// hashCode, enums, data classes, comparators, Pair/Triple, Result, lazy, preconditions. (kotlin.random:
// d_random_time.kt, d_random_api.kt)
// difftest: heap 32768 -- the default 16 KB runs out: one long main keeps the objects of its checks alive
// difftest: large -- hashing, enums, comparators, Result and lazy in one program: about 280 KB of flash

data class Pt(val x: Int, val y: Double, val name: String?, val tags: List<String>)
data class Box<T>(val v: T)
enum class Color { RED, GREEN, BLUE }

fun err(label: String, block: () -> Any?) {
    val r = runCatching(block)
    val e = r.exceptionOrNull()
    println("$label: " + if (e == null) "ok ${r.getOrNull()}" else "${e::class.simpleName}: ${e.message}")
}

var lazyCount = 0
val lz: String by lazy { lazyCount++; "lazy-value" }

fun main() {
    // hashCode values (must equal the host's)
    println("hash String: ${"".hashCode()} ${"hello".hashCode()} ${"Kotlin/Native on Cortex-M4".hashCode()}")
    println("hash Int/Long: ${0.hashCode()} ${(-1).hashCode()} ${Int.MIN_VALUE.hashCode()} ${0L.hashCode()} ${(-1L).hashCode()} ${Long.MAX_VALUE.hashCode()} ${(1L shl 32).hashCode()} ${123456789012345L.hashCode()}")
    println("hash Double/Float: ${0.0.hashCode()} ${(-0.0).hashCode()} ${1.5.hashCode()} ${Double.NaN.hashCode()} ${0.1.hashCode()} ${1.5f.hashCode()} ${Float.NaN.hashCode()} ${(-0.0f).hashCode()}")
    println("hash Boolean/Char/Byte/Short: ${true.hashCode()} ${false.hashCode()} ${'a'.hashCode()} ${'日'.hashCode()} ${(-3).toByte().hashCode()} ${(-3).toShort().hashCode()}")
    val pt = Pt(3, 2.5, "p", listOf("x", "y")); val ptNull = Pt(-1, -0.0, null, emptyList())
    println("hash data: ${pt.hashCode()} ${ptNull.hashCode()} ${Box(null).hashCode()} ${Box(Box(1)).hashCode()} ${Box(intArrayOf(1)).equals(Box(intArrayOf(1)))} ${Pair(1, "a").hashCode()} ${Triple(1, 2.0, 'c').hashCode()}")
    println("hash collections: ${listOf(1, 2, 3).hashCode()} ${emptyList<Int>().hashCode()} ${listOf("a", null).hashCode()} ${setOf(1, 2, 3).hashCode()} ${mapOf("a" to 1, "b" to 2).hashCode()} ${mapOf(1 to null).hashCode()} ${arrayListOf(listOf(1), setOf(2)).hashCode()} ${ArrayDeque(listOf(1, 2, 3)).hashCode()} ${(1..10).hashCode()} ${('a'..'z').hashCode()} ${(1L..5L).hashCode()} ${(1..0).hashCode()}")
    println("hash enum ordinal-ish: ${Color.GREEN.ordinal} ${Color.valueOf("BLUE")} ${Color.entries} ${Color.values().size} ${enumValues<Color>().last()} ${Color.RED.compareTo(Color.BLUE)} ${Color.GREEN.name}")
    err("enum valueOf bad") { Color.valueOf("PINK") }
    println("data toString/eq/copy: $pt $ptNull ${pt == pt.copy()} ${pt == pt.copy(tags = listOf("x"))} ${pt.copy(name = null)} ${pt.component4()} ${Box("s")}")
    // comparators
    val words = listOf("pear", "Fig", "apple", "kiwi", "Banana", "fig", null, "date")
    println("naturalOrder: ${words.filterNotNull().sortedWith(naturalOrder())} reverseOrder: ${words.filterNotNull().sortedWith(reverseOrder())}")
    println("nullsFirst: ${words.sortedWith(nullsFirst())} nullsLast: ${words.sortedWith(nullsLast(compareBy<String> { it.length }))} nullsFirst(ci): ${words.sortedWith(nullsFirst(String.CASE_INSENSITIVE_ORDER))}")
    println("compareBy multi: ${words.filterNotNull().sortedWith(compareBy({ it.length }, { it.lowercase() }, { it }))} thenBy: ${words.filterNotNull().sortedWith(compareBy<String> { it.first().lowercaseChar() }.thenBy { it.length }.thenDescending(naturalOrder()))}")
    println("reversed cmp: ${words.filterNotNull().sortedWith(compareBy<String> { it.length }.reversed())} compareValues: ${compareValues("a", "b")} ${compareValues(null, 1)} ${compareValuesBy(Pt(1, 0.0, "a", listOf()), Pt(1, 0.0, "b", listOf()), { it.x }, { it.name })}")
    println("maxWith/minOf: ${words.filterNotNull().maxWithOrNull(compareBy { it.length })} ${words.filterNotNull().minOf { it.length }} ${words.filterNotNull().maxOfWith(String.CASE_INSENSITIVE_ORDER) { it }} sorted stable: ${listOf("b1", "a1", "b2", "a2", "b3").sortedBy { it[0] }}")
    // Pair / Triple / to
    val p = "k" to 1; val t = Triple("a", 2, 3.0)
    println("pair: $p ${p.first} ${p.second} ${p.toList()} ${p.copy(second = 9)} triple: $t ${t.third} ${t.toList()} ${(1 to 2) to 3} ${p.let { (a, b) -> a + b }}")
    // Result
    val ok: Result<Int> = runCatching { 10 }
    val bad: Result<Int> = runCatching { error("boom") }
    println("result: $ok $bad ${ok.isSuccess} ${bad.isFailure} ${ok.getOrNull()} ${bad.getOrNull()} ${bad.exceptionOrNull()?.message} ${bad.getOrElse { -1 }} ${bad.getOrDefault(-2)}")
    println("result fold: ${ok.fold({ "v$it" }, { "e${it.message}" })} ${bad.fold({ "v$it" }, { "e${it.message}" })} map=${ok.map { it * 2 }} mapCatching=${ok.mapCatching { check(it < 5) { "too big" }; it }.exceptionOrNull()?.message} recover=${bad.recover { 7 }} recoverCatching=${bad.recoverCatching { throw IllegalStateException("again") }.exceptionOrNull()?.message} onSuccess=${ok.onSuccess { }.onFailure { }.getOrThrow()}")
    println("result success/failure: ${Result.success("x")} ${Result.failure<String>(IllegalArgumentException("ia")).exceptionOrNull()?.let { it::class.simpleName }} ${runCatching { "x".toInt() }.exceptionOrNull()?.let { it::class.simpleName }}")
    err("getOrThrow") { bad.getOrThrow() }
    // lazy
    println("lazy: ${lazyCount} $lz $lz ${lazyCount} ${lazyOf(5).value} ${lazyOf(5).isInitialized()}")
    val lz2 = lazy(LazyThreadSafetyMode.NONE) { "none-mode" }; println("lazy NONE: ${lz2.isInitialized()} ${lz2.value} ${lz2.isInitialized()} $lz2")
    val lz3 = lazy(LazyThreadSafetyMode.PUBLICATION) { 3 }; println("lazy PUBLICATION: ${lz3.value}")
    var attempts = 0
    val failing = lazy { attempts++; if (attempts < 2) throw IllegalStateException("first fails") else "second ok" }
    err("lazy fail 1") { failing.value }
    err("lazy fail 2") { failing.value }
    // misc scope functions / takeIf / also / repeat / TODO
    println("scope: ${5.let { it * 2 }} ${StringBuilder().apply { append("ap") }} ${"x".run { length }} ${with(listOf(1, 2)) { size }} ${3.takeIf { it > 2 }} ${3.takeUnless { it > 2 }} ${"a".also { }}")
    err("TODO") { TODO("later") }
    err("require") { require(false) { "req msg" } }
    err("requireNotNull") { requireNotNull(null as String?) { "nn msg" } }
    err("checkNotNull") { checkNotNull(null as String?) }
    err("error") { error("err msg") }
    err("NPE !!") { (null as String?)!!.length }
    err("ClassCast") { (opaqueAny("s") as Int) + 1 }
    err("as? ok") { opaqueAny("s") as? Int }
    println("done")
}

fun opaqueAny(v: Any): Any = listOf(v).first()
