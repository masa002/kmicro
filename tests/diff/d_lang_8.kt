// Language probe 8: corner cases: bridges, diamonds, init-order pitfalls, exceptions in finally/lazy/init,
// overloads, collisions in string when, comparators, identity keys, captured loop variables.
// difftest: heap 49152 -- one long main keeps the objects of its checks alive, and the free memory ends up in
// small pieces: 40 KB runs out
// difftest: large -- that heap leaves 8 KB of the STM32L431's RAM for the stack, and the program takes 10 KB

interface Producer<out T> { fun get(): T }
class IntProducer(private val v: Int) : Producer<Int> { override fun get(): Int = v }
abstract class Transform<T> { abstract fun apply(x: T): T; fun twice(x: T) = apply(apply(x)) }
class Inc : Transform<Int>() { override fun apply(x: Int) = x + 1 }
open class Animal { open fun self(): Animal = this; override fun toString() = "Animal" }
class Dog : Animal() { override fun self(): Dog = this; fun bark() = "woof"; override fun toString() = "Dog" }

interface A { fun f() = "A"; val p: String get() = "pA" }
interface B { fun f() = "B" }
class AB : A, B { override fun f() = super<A>.f() + super<B>.f(); override val p = "pAB" }
interface WithConst { companion object { const val K = 7; fun make() = "made" } }
class Impl : WithConst

abstract class Pitfall { init { println("Pitfall sees ${describe()}") }; abstract fun describe(): String }
class Sub(val name: String) : Pitfall() { override fun describe() = "name=" + listOf<Any?>(name) }

class Fails(val v: Int) { init { if (v < 0) throw IllegalArgumentException("negative") } }

var lazyAttempts = 0
val flaky: String by lazy { lazyAttempts++; if (lazyAttempts < 2) error("first attempt fails"); "ok after $lazyAttempts" }

fun over(x: Int) = "Int"
fun over(x: Long) = "Long"
fun over(x: Any) = "Any"
fun over(x: Int?) = "Int?"
fun over(x: String, vararg rest: String) = "String+${rest.size}"
fun over(x: Double = 1.0, y: Int = 2) = "Double $x $y"

class Weird { override fun toString(): String = throw IllegalStateException("toString failed") }

data class Emp(val dept: String, val name: String, val age: Int)
class Key(val k: Int)
class EqKey(val k: Int) { override fun equals(other: Any?) = other is EqKey && other.k == k; override fun hashCode() = k % 3 }
class Triple3(val a: Int, val b: Int, val c: Int) { operator fun component1() = a; operator fun component2() = b; operator fun component3() = c }

operator fun Dog?.plus(o: Dog?): String = "${this ?: "none"}+${o ?: "none"}"

fun fin1(): String {
    val log = StringBuilder()
    try {
        try { throw IllegalStateException("first") } finally { log.append("finally-runs ") }
    } catch (e: IllegalStateException) { log.append("caught ${e.message}") }
    return log.toString()
}

fun fin2(): String = try {
    try { throw IllegalStateException("original") } finally { throw IllegalArgumentException("from finally") }
} catch (e: Exception) { "${e::class.simpleName} ${e.message}" }

fun fin3(): String = try {
    try { throw IllegalStateException("outer") } finally {
        val inner = try { throw ArithmeticException("inner") } catch (e: ArithmeticException) { e.message }
        print("[inner $inner] ")
    }
} catch (e: Exception) { "${e::class.simpleName} ${e.message}" }

@Suppress("RETURN_IN_FINALLY", "UNREACHABLE_CODE")
fun fin4(): Int { try { throw IllegalStateException("lost") } finally { return 42 } }

fun fin5(): String {
    val r = StringBuilder()
    for (i in 0..3) {
        try { if (i % 2 == 0) continue; if (i == 3) break; r.append("body$i ") } finally { r.append("f$i ") }
    }
    return r.toString()
}

fun catchInCatch(): String = try { error("a") } catch (e: Exception) {
    try { error("b:" + e.message) } catch (e2: Exception) { "nested ${e2.message}" }
}

fun rethrow(): String = try {
    try { error("x") } catch (e: IllegalStateException) { throw RuntimeException("wrapped", e) }
} catch (e: RuntimeException) { "${e.message} <- ${e.cause?.message}" }

fun deep(n: Int): Int = if (n == 0) throw IllegalStateException("bottom") else deep(n - 1) + 1

fun main() {
    println("== bridges / covariance")
    val pr: Producer<Any> = IntProducer(5)
    println(pr.get())
    val tr: Transform<Int> = Inc()
    println(tr.twice(1))
    val an: Animal = Dog()
    println("${an.self()} ${Dog().self().bark()}")
    val ab = AB()
    println("${ab.f()} ${ab.p} ${(ab as A).p} ${WithConst.K} ${WithConst.make()} ${Impl() is WithConst}")

    println("== init-order pitfall")
    println(Sub("x").describe())
    println(runCatching { Fails(-1) }.exceptionOrNull()?.message)
    println(Fails(1).v)

    println("== lazy failure and retry")
    println(runCatching { flaky }.exceptionOrNull()?.message)
    println(runCatching { flaky }.getOrNull())

    println("== overloads")
    val ni: Int? = 3
    println("${over(1)} ${over(1L)} ${over("s")} ${over("s", "t", "u")} ${over(ni)} ${over(2.0)} ${over(y = 5)} ${over('c')} ${over(1.5f)}")

    println("== exceptions in odd places")
    println(fin1())
    println(fin2())
    println(fin3())
    println(fin4())
    println(fin5())
    println(catchInCatch())
    println(rethrow())
    println(runCatching { "value: ${Weird()}" }.exceptionOrNull()?.message)
    println(runCatching { deep(200) }.exceptionOrNull()?.message)
    val seqErr = runCatching { sequence { yield(1); error("in sequence") }.toList() }.exceptionOrNull()?.message
    println(seqErr)
    val inlineErr = runCatching { listOf(1, 2, 3).map { if (it == 2) throw ArithmeticException("at $it") else it } }
    println(inlineErr.exceptionOrNull()?.message)
    var cleanups = 0
    repeat(50) { runCatching { try { throw Exception("e$it") } finally { cleanups++ } } }
    println("cleanups $cleanups")
    val msgs = (1..30).map { i -> runCatching { if (i % 3 == 0) error("e$i") else i }.fold({ "$it" }, { it.message!! }) }
    println(msgs.joinToString(","))

    println("== string when with hash collisions")
    println("Aa".hashCode() == "BB".hashCode())
    for (s in listOf("Aa", "BB", "C", "")) print(when (s) { "Aa" -> "aa "; "BB" -> "bb "; "" -> "empty "; else -> "other " })
    println()

    println("== comparators")
    val emps = listOf(Emp("eng", "zed", 30), Emp("ops", "amy", 25), Emp("eng", "bob", 30), Emp("eng", "cat", 22))
    println(emps.sortedWith(compareBy<Emp>({ it.dept }, { -it.age }).thenBy { it.name }).map { it.name })
    println(emps.sortedWith(compareByDescending<Emp> { it.age }.thenByDescending { it.name }).map { it.name })
    println(emps.sortedBy { it.name }.reversed().map { it.name })
    println(emps.groupBy { it.dept }.mapValues { (_, v) -> v.maxOf { it.age } })
    println(emps.maxWithOrNull(Comparator { a, b -> a.name.length - b.name.length + a.age.compareTo(b.age) })?.name)
    println(emps.sortedWith(nullsFirst(compareBy<Emp> { it.age })).first().name)

    println("== identity keys")
    val k1 = Key(1); val k2 = Key(1)
    val idMap = hashMapOf(k1 to "one", k2 to "uno")
    println("${idMap.size} ${idMap[k1]} ${idMap[k2]} ${idMap[Key(1)]}")
    val eqSet = hashSetOf(EqKey(1), EqKey(4), EqKey(1), EqKey(7))
    println("${eqSet.size} ${EqKey(4) in eqSet} ${EqKey(5) in eqSet}")
    val anySet = HashSet<Any>()
    repeat(100) { anySet += Any() }
    println(anySet.size)

    println("== captures / destructuring / nullable operators")
    val fns = mutableListOf<() -> Int>()
    for (i in 1..3) fns += { i * 100 }
    var j = 0
    val fnsVar = mutableListOf<() -> Int>()
    while (j < 3) { val jj = j; fnsVar += { jj }; j++ }
    println("${fns.map { it() }} ${fnsVar.map { it() }}")
    val (x, _, z) = Triple3(1, 2, 3)
    println("$x $z")
    val nd: Dog? = null
    println("${nd + Dog()} ${Dog() + nd}")
    println(emptyList<Nothing>().size + listOf<Nothing?>(null).size)

    println("== range edges")
    var count = 0
    for (i in Int.MAX_VALUE - 2..Int.MAX_VALUE) count++
    for (i in Int.MIN_VALUE downTo Int.MIN_VALUE) count++
    println(count)
    println((Long.MAX_VALUE - 1..Long.MAX_VALUE).count())
    println(('z' downTo 'u' step 2).joinToString(""))
    println((1..10).reversed().step(3).toList())
    println((5 downTo 1).reversed().toList())
    println(IntRange.EMPTY.toList() + (3..1).toList())

    println("== string building under GC")
    var s = ""
    for (i in 0 until 300) s += i % 10
    println("${s.length} ${s.takeLast(12)} ${s.hashCode()}")
    val big = buildString { repeat(2000) { append(('a' + it % 26)) } }
    println("${big.length} ${big.substring(1990)} ${big.count { it == 'z' }}")
    println("done")
}
