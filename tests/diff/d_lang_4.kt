// Language probe 4: functions, operators, lambdas, references, inline, scope functions, DSL builders.
import kotlin.reflect.KFunction
import kotlin.reflect.KProperty0
import kotlin.reflect.KProperty1

fun String.shout(): String = uppercase() + "!"
val String.vowels: Int get() = count { it in "aeiou" }
var StringBuilder.lastChar: Char
    get() = this[length - 1]
    set(v) { this[length - 1] = v }
fun Int?.orZero(): Int = this ?: 0
infix fun Int.pow(e: Int): Long { var r = 1L; repeat(e) { r *= this }; return r }

data class Vec(val x: Int, val y: Int) : Comparable<Vec> {
    operator fun plus(o: Vec) = Vec(x + o.x, y + o.y)
    operator fun minus(o: Vec) = Vec(x - o.x, y - o.y)
    operator fun times(k: Int) = Vec(x * k, y * k)
    operator fun div(k: Int) = Vec(x / k, y / k)
    operator fun rem(k: Int) = Vec(x % k, y % k)
    operator fun unaryMinus() = Vec(-x, -y)
    operator fun unaryPlus() = this
    operator fun not() = Vec(y, x)
    operator fun inc() = Vec(x + 1, y + 1)
    operator fun dec() = Vec(x - 1, y - 1)
    operator fun get(i: Int) = if (i == 0) x else y
    operator fun contains(v: Int) = v == x || v == y
    operator fun rangeTo(o: Vec) = VecRange(this, o)
    operator fun rangeUntil(o: Vec) = VecRange(this, Vec(o.x - 1, o.y - 1))
    override fun compareTo(other: Vec) = compareValuesBy(this, other, { it.x }, { it.y })
    operator fun invoke(s: String) = "$s$x,$y"
}
operator fun Int.times(v: Vec) = v * this

class VecRange(val a: Vec, val b: Vec) : Iterable<Vec> {
    override fun iterator(): Iterator<Vec> = object : Iterator<Vec> {
        var cur = a
        override fun hasNext() = cur <= b
        override fun next(): Vec { val r = cur; cur = Vec(cur.x + 1, cur.y + 1); return r }
    }
}

class Grid(val w: Int, val h: Int) {
    private val cells = IntArray(w * h)
    operator fun get(x: Int, y: Int) = cells[y * w + x]
    operator fun set(x: Int, y: Int, v: Int) { cells[y * w + x] = v }
    operator fun iterator(): Iterator<Int> = cells.iterator()
}

class Acc(var total: Int = 0) {
    operator fun plusAssign(v: Int) { total += v }
    operator fun minusAssign(v: Int) { total -= v }
}

tailrec fun gcd(a: Long, b: Long): Long = if (b == 0L) a else gcd(b, a % b)
tailrec fun countDown(n: Int, acc: Int = 0): Int = if (n == 0) acc else countDown(n - 1, acc + n)

fun interface Pred { fun test(x: Int): Boolean }
fun interface Transformer<A, B> { fun apply(a: A): B }
fun applyPred(p: Pred, xs: List<Int>) = xs.filter { p.test(it) }

fun twice(x: Int) = x * 2
class Calc(val base: Int) {
    fun add(x: Int) = base + x
    val doubled get() = base * 2
    companion object { fun make(b: Int) = Calc(b) }
}
var topVar = 10
val topVal = "tv"

inline fun findFirst(xs: List<Int>, p: (Int) -> Boolean): Int? {
    for (x in xs) if (p(x)) return x
    return null
}
fun firstEven(xs: List<Int>): Int {
    xs.forEach { if (it % 2 == 0) return it }
    return -1
}
inline fun runTwice(crossinline f: () -> Unit) { val r = Runnable2 { f() }; r.run(); r.run() }
fun interface Runnable2 { fun run() }
inline fun withStored(a: () -> Int, noinline b: () -> Int): Pair<Int, () -> Int> = a() to b

@DslMarker annotation class HtmlDsl
@HtmlDsl class Tag(val name: String) {
    val children = mutableListOf<Tag>()
    val attrs = linkedMapOf<String, String>()
    var text = ""
    fun tag(n: String, init: Tag.() -> Unit) { children += Tag(n).apply(init) }
    operator fun String.unaryPlus() { text += this }
    infix fun String.eq(v: String) { attrs[this] = v }
    fun render(): String = "<$name${attrs.entries.joinToString("") { " ${it.key}=\"${it.value}\"" }}>" + text +
        children.joinToString("") { it.render() } + "</$name>"
}
fun html(init: Tag.() -> Unit): Tag = Tag("html").apply(init)

fun buildStr(block: StringBuilder.() -> Unit): String = StringBuilder().apply(block).toString()

fun counter(): () -> Int { var c = 0; return { ++c } }

fun takesSuspend(f: suspend (Int) -> String): String = if (f is Function<*>) "suspend fn ok" else "?"

fun main() {
    println("== extensions")
    println("hello".shout() + " " + "education".vowels)
    val sb = StringBuilder("abc"); sb.lastChar = 'Z'
    println("$sb ${sb.lastChar}")
    val ni: Int? = null
    println("${ni.orZero()} ${5.orZero()} ${2 pow 10}")

    println("== operators")
    var v = Vec(1, 2)
    println("${v + Vec(3, 4)} ${v - Vec(1, 1)} ${v * 3} ${3 * v} ${Vec(9, 7) / 2} ${Vec(9, 7) % 4}")
    println("${-v} ${+v} ${!v} ${v[0]} ${v[1]} ${2 in v} ${5 in v} ${5 !in v}")
    v++; println(v); v--; println(v); ++v; println(v)
    println((Vec(0, 0)..Vec(2, 2)).toList())
    println((Vec(0, 0)..<Vec(2, 2)).toList())
    println("${Vec(1, 1) < Vec(1, 2)} ${Vec(2, 0) > Vec(1, 9)} ${maxOf(Vec(1, 1), Vec(0, 5))}")
    println(v("at "))
    val g = Grid(3, 2); g[1, 1] = 5; g[2, 0] = 7
    println("${g[1, 1]} ${g[2, 0]} ${g.toList2()}")
    val acc = Acc(); acc += 5; acc += 3; acc -= 1
    println(acc.total)
    val ml = mutableListOf(1); ml += 2; ml += listOf(3, 4); ml -= 1
    println(ml)
    var il = listOf(1); il += 2
    println(il)
    var s = "a"; s += "b"; s += 1
    println(s)
    println("${v == Vec(2, 3)} ${v != Vec(2, 3)} ${v === v}")

    println("== tailrec / local")
    println(gcd(1071L, 462L))
    println(countDown(100000))
    fun fact(n: Int): Long = if (n <= 1) 1 else n * fact(n - 1)
    println(fact(20))
    var hits = 0
    fun hit(k: Int) { hits += k }
    hit(2); hit(3)
    println(hits)

    println("== lambdas / closures")
    val add: (Int, Int) -> Int = { a, b -> a + b }
    val sq = fun(x: Int): Int { return x * x }
    println("${add(2, 3)} ${sq(7)} ${add.invoke(1, 1)}")
    val c1 = counter(); val c2 = counter()
    println("${c1()} ${c1()} ${c1()} ${c2()}")
    var sum = 0
    listOf(1, 2, 3).forEach { sum += it }
    println(sum)
    val fns = (1..3).map { i -> { i * 10 } }
    println(fns.map { it() })
    val nullableFn: ((Int) -> Int)? = null
    println(nullableFn?.invoke(1) ?: "no fn")
    val withRecv: Int.(Int) -> Int = { this * it }
    println("${3.withRecv(4)} ${withRecv(5, 6)}")
    val curried = { a: Int -> { b: Int -> a - b } }
    println(curried(10)(3))
    println(listOf("bb", "a", "ccc").sortedBy { it.length })
    println(listOf(1, 2, 3).fold(0) { a, x -> a + x * x })
    val unitFn: () -> Unit = {}
    println(unitFn())
    println(takesSuspend { "x$it" })

    println("== references")
    val f1 = ::twice
    println("${f1(4)} ${listOf(1, 2).map(::twice)} ${f1.name}")
    val calc = Calc(100)
    val bound = calc::add
    val unbound = Calc::add
    println("${bound(1)} ${unbound(calc, 2)} ${listOf(1, 2).map(calc::add)}")
    val ctor = ::Calc
    println(ctor(7).base)
    println(listOf(1, 2).map(::Vec.let { f -> { i: Int -> f(i, i) } }))
    val prop: KProperty1<Calc, Int> = Calc::doubled
    println("${prop.get(calc)} ${prop.name} ${prop(calc)}")
    val tv: KProperty0<Int> = ::topVar
    println("${tv.get()} ${tv.name} ${::topVal.get()}")
    val mtv = ::topVar
    mtv.set(11)
    println(topVar)
    println(listOf("a", "bb").map(String::length))
    println(listOf(Vec(1, 2)).map(Vec::x))
    val boundProp = calc::base
    println("${boundProp.get()} ${boundProp.name}")
    val kf: KFunction<Int> = ::twice
    println(kf.name)
    println(Calc.Companion::make.invoke(3).base)
    val eqRef = ::twice == ::twice
    println(eqRef)

    println("== fun interfaces")
    val even = Pred { it % 2 == 0 }
    println(applyPred(even, (1..6).toList()))
    println(applyPred({ it > 4 }, (1..6).toList()))
    val tr = Transformer<Int, String> { "<$it>" }
    println(tr.apply(5))
    val r2 = Runnable2 { println("r2 ran") }
    r2.run()

    println("== inline / non-local / labels")
    println(findFirst(listOf(1, 3, 6, 7)) { it > 4 })
    println(firstEven(listOf(1, 3, 8, 9)))
    runTwice { print("tw ") }
    println()
    val (a1, b1) = withStored({ 1 }, { 2 })
    println("$a1 ${b1()}")
    val out = mutableListOf<Int>()
    listOf(1, 2, 3, 4).forEach lit@{ if (it == 2) return@lit; out += it }
    listOf(5, 6).forEach { if (it == 5) return@forEach; out += it }
    println(out)
    outer@ for (i in 1..3) {
        for (j in 1..3) {
            if (j == 2) continue@outer
            if (i == 3) break@outer
            print("$i$j ")
        }
    }
    println()
    val r = run block@{ if (out.size > 2) return@block "big"; "small" }
    println(r)
    for (i in 0..5) {
        listOf(1).forEach { if (i == 1) continue; if (i == 3) break }
        print("nl$i ")
    }
    println()

    println("== scope functions")
    val n: String? = "kot"
    println(n?.let { it.length } ?: 0)
    println(with(StringBuilder()) { append("w"); append(1); toString() })
    println("x".run { this + length })
    val list = mutableListOf<Int>().apply { add(1); add(2) }.also { println("also ${it.size}") }
    println(list)
    println("${5.takeIf { it > 3 }} ${5.takeIf { it > 9 }} ${5.takeUnless { it > 3 }}")
    println(run { 42 })

    println("== DSL")
    val doc = html {
        tag("body") {
            "class" eq "main"
            tag("p") { +"Hello" }
            tag("p") { +"World"; "id" eq "w" }
        }
    }
    println(doc.render())
    println(buildStr { append("a"); append('b'); append(3) })
    println(buildString { append("bs"); repeat(3) { append(it) } })
    println(buildList { add(1); addAll(listOf(2, 3)) })
    println(buildMap { put("k", 1); put("j", 2) })
    println("done")
}

fun Grid.toList2(): List<Int> { val r = mutableListOf<Int>(); for (c in this) r += c; return r }
