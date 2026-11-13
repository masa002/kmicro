// Language probe 5: control flow, smart casts, null safety, casts, ranges, strings and templates.
// difftest: heap 32768 -- one long main: its frame keeps the objects of every check alive until it returns

sealed interface Shape
data class Circle(val r: Double) : Shape
data class Sq(val side: Double) : Shape
data object Empty : Shape

fun classify(x: Any?): String = when (x) {
    null -> "null"
    is Int if x > 100 -> "big int"
    is Int -> "int $x"
    is String if x.isEmpty() -> "empty string"
    is String -> "string of ${x.length}"
    in listOf(1.5, 2.5) -> "listed double"
    is List<*> -> "list ${x.size}"
    else -> "other ${x::class.simpleName}"
}

fun grade(n: Int) = when (n) {
    in 90..100 -> "A"
    in 80..<90 -> "B"
    !in 0..100 -> "invalid"
    50, 60, 70 -> "round"
    else -> "C"
}

fun area(s: Shape) = when (s) {
    is Circle -> 3 * s.r * s.r
    is Sq -> s.side * s.side
    Empty -> 0.0
}

fun sign(n: Int) = when {
    n < 0 -> -1
    n > 0 -> 1
    else -> 0
}

fun strLen(x: Any): Int {
    if (x !is String) return -1
    return x.length                    // smart cast
}

class Node(val value: Int, val next: Node?)

fun parseOr(s: String): Int = try { s.toInt() } catch (e: NumberFormatException) { -1 } finally { print("[f]") }

fun main() {
    println("== when")
    println(listOf(null, 5, 500, "", "abc", 1.5, 3.5, listOf(1, 2)).map(::classify))
    println(listOf(95, 85, 70, 20, 101, -1).map(::grade))
    println(listOf(Circle(1.0), Sq(2.0), Empty).map(::area))
    println("${sign(-5)} ${sign(0)} ${sign(9)}")
    val c = 'q'
    println(when (c) { in 'a'..'m' -> "first half"; in 'n'..'z' -> "second half"; else -> "?" })
    val s = "two"
    println(when (s) { "one" -> 1; "two" -> 2; else -> 0 })
    val res = when (val len = s.length) { 3 -> "three ($len)"; else -> "len $len" }
    println(res)

    println("== smart casts / null safety")
    println("${strLen("abcd")} ${strLen(4)}")
    val maybe: String? = if (s.length > 2) "yes" else null
    if (maybe != null) println(maybe.length)
    val list = Node(1, Node(2, Node(3, null)))
    println(list.next?.next?.value)
    println(list.next?.next?.next?.value)
    println(list.next?.next?.next?.value ?: "end")
    var cur: Node? = list
    var total = 0
    while (cur != null) { total += cur.value; cur = cur.next }
    println(total)
    val nothing: String? = null
    val npe = runCatching { nothing!!.length }.exceptionOrNull()
    println("${npe?.let { it::class.simpleName }}: ${npe?.message}")
    val anyS: Any = "str"
    val asInt = anyS as? Int
    println(asInt)
    val cce = runCatching { anyS as Int }.exceptionOrNull()
    println("${cce?.let { it::class.simpleName }}: ${cce?.message}")
    val cce2 = runCatching { (listOf(1) as Any) as String }.exceptionOrNull()
    println("${cce2?.let { it::class.simpleName }}: ${cce2?.message}")
    val cce3 = runCatching { val x: Any = Circle(1.0); x as Shape; x as Sq }.exceptionOrNull()
    println("${cce3?.let { it::class.simpleName }}: ${cce3?.message}")
    val nullCast = runCatching { val x: Any? = null; x as String }.exceptionOrNull()
    println("${nullCast?.let { it::class.simpleName }}: ${nullCast?.message}")
    println(null as String?)
    val e = (anyS as? String)?.uppercase() ?: "none"
    println(e)
    val len = maybe?.length ?: throw IllegalStateException("no")
    println(len)

    println("== loops / ranges")
    for (i in 1..5) print(i); println()
    for (i in 1 until 5) print(i); println()
    for (i in 1..<5) print(i); println()
    for (i in 10 downTo 1 step 3) print("$i "); println()
    for (i in 0..20 step 5) print("$i "); println()
    for (i in (1..4).reversed()) print(i); println()
    for (ch in 'a'..'e') print(ch); println()
    for (ch in 'a'..'z' step 5) print(ch); println()
    for (l in 1L..3L) print(l); println()
    for (i in IntProgression.fromClosedRange(0, 10, 4)) print(i); println()
    println((1..10).sum().toString() + " " + (1..10 step 2).toList() + " " + (10 downTo 0 step 4).last)
    println("${5 in 1..10} ${11 in 1..10} ${(1..0).isEmpty()} ${(1..10).count { it % 3 == 0 }}")
    println("${(0..<0).isEmpty()} ${(1..5).first} ${(1..5).last} ${(1..5 step 2).step}")
    println(1.0..2.0)
    println(1.5 in 1.0..2.0)
    println((1..3).toString() + " " + (3 downTo 1).toString() + " " + ('a'..'c').toString())
    val arr = arrayOf("x", "y", "z")
    for ((idx, v) in arr.withIndex()) print("$idx$v "); println()
    for (idx in arr.indices) print(idx); println()
    for (idx in arr.indices.reversed()) print(arr[idx]); println()
    var k = 0
    do { k += 3 } while (k < 10)
    println(k)
    var w = 100
    while (true) { w /= 3; if (w < 5) break }
    println(w)
    repeat(3) { print("r$it ") }; println()
    println(parseOr("12") + parseOr("x"))
    val tr = try { "ok".toInt() } catch (ex: Exception) { ex::class.simpleName }
    println(tr)

    println("== strings")
    val name = "World"
    val items = listOf(1, 2)
    println("Hello, $name! ${name.length} ${items.size + 1} ${if (items.isEmpty()) "none" else items.joinToString("+")}")
    println("escape: \$name \"q\" \\ \t|tab ${'$'}x é 😀")
    val raw = """
        |line one
        |  line two $name
        |line ${1 + 2}
        """.trimMargin()
    println(raw)
    val ind = """
        alpha
          beta
        gamma
    """.trimIndent()
    println(ind)
    println("""raw "quotes" and \n no escape""")
    val json = $$"""{"name": "$$name", "price": "$5", "tpl": "${x}"}"""
    println(json)
    val dd = $$"cost $${items.size} $x"
    println(dd)
    println("a" + 1 + 2 + 'c' + null + 1.5 + true)
    println(1.toString() + "x".repeat(3) + "abc".reversed() + "Kotlin"[0] + "Kotlin".substring(1, 3))
    val ch = 'A'
    println("${ch + 2} ${ch.code} ${'z' - 'a'} ${(ch.code + 1).toChar()} ${'9'.digitToInt()} ${ch.lowercaseChar()} ${'b'.uppercase()}")
    println("${'x' < 'y'} ${ch.isLetter()} ${'5'.isDigit()} ${' '.isWhitespace()} ${'\n'.isWhitespace()}")
    println("a,b,,c".split(",") + " " + "  pad  ".trim() + "|" + "x".padStart(3, '.') + "|" + "%")
    println("Kotlin".let { "${it.first()}${it.last()}${it.length}" })
    println("cmp ${"abc" < "abd"} ${"abc".compareTo("ab")} ${"a" == "a"} ${"Ab".equals("aB", ignoreCase = true)}")
    println("ÄÖÜ ß straße".uppercase() + " " + "ÀÉÎ".lowercase())
    println("done")
}
