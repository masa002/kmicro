// Language probe 11: remaining syntax: property overrides and super, companion as value, delegation to objects,
// extension shadowing, unicode and backtick names, Duration formatting, long literals, big string when.
// (Duration.toString(unit, decimals): d_known_duration_format.kt; a public backtick name: d_known_backtick_name.kt)
// difftest: large -- Duration.parse uses String.toDouble, which links the Regex engine (about 240 KB of flash)
import kotlin.time.Duration
import kotlin.time.Duration.Companion.microseconds
import kotlin.time.Duration.Companion.milliseconds
import kotlin.time.Duration.Companion.minutes
import kotlin.time.Duration.Companion.seconds

open class Named { open val name: String = "named"; open val size: Int get() = 1 }
class Renamed : Named() { override var name: String = "renamed"; override val size: Int get() = super.size + 10 }

interface Factory<T> { fun create(): T }
class Widget(val id: Int) {
    companion object : Factory<Widget> { private var next = 0; override fun create() = Widget(++next) }
}
fun <T> makeTwo(f: Factory<T>) = listOf(f.create(), f.create())

interface Speaker { fun speak(): String; fun loud() = speak().uppercase() }
object Quiet : Speaker { override fun speak() = "psst" }
class Delegated : Speaker by Quiet
abstract class Shape(val sides: Int) { abstract fun label(): String }
object Triangle : Shape(3) { override fun label() = "triangle/$sides" }

class Member { fun hello() = "member" }
fun Member.hello() = "extension"           // shadowed: the member wins
fun Member.other() = "ext other"

fun interface Op { fun run(x: Int): Int; fun twice(x: Int) = run(run(x)) }

enum class Planet(val g: Double) : Speaker { EARTH(9.8), MARS(3.7); override fun speak() = "$name g=$g" }

infix fun Int.divmod(d: Int) = Pair(this / d, this % d)

class Outer(val tag: String) {
    inner class Inner(val tag: String) {
        fun tags() = buildString { with(StringBuilder("x")) { append(this@Inner.tag); append(this@Outer.tag); this@buildString.append(toString()) } }
    }
}

private fun `name with spaces`() = "backticks ok"   // public: the C export of -p static fails (api.cpp)
val π = 3.14159
fun firstOrReturn(xs: List<Int>): String { val f = xs.firstOrNull() ?: return "empty"; return "first $f" }

fun word(n: Int): String = when ("w$n") {
    "w0" -> "zero"; "w1" -> "one"; "w2" -> "two"; "w3" -> "three"; "w4" -> "four"; "w5" -> "five"; "w6" -> "six"
    "w7" -> "seven"; "w8" -> "eight"; "w9" -> "nine"; "w10" -> "ten"; "w11" -> "eleven"; "w12" -> "twelve"
    "w13" -> "thirteen"; "w14" -> "fourteen"; "w15" -> "fifteen"; "w16" -> "sixteen"; "w17" -> "seventeen"
    "w18" -> "eighteen"; "w19" -> "nineteen"; "w20" -> "twenty"; else -> "many"
}

const val LONG_TEXT = "Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed do eiusmod tempor incididunt ut labore et " +
    "dolore magna aliqua. Ut enim ad minim veniam, quis nostrud exercitation ullamco laboris nisi ut aliquip ex ea commodo " +
    "consequat. Duis aute irure dolor in reprehenderit in voluptate velit esse cillum dolore eu fugiat nulla pariatur."

fun main() {
    println("== overrides / companion / delegation")
    val r = Renamed(); r.name = "changed"
    val n: Named = r
    println("${n.name} ${n.size} ${Named().size}")
    println(makeTwo(Widget).map { it.id } + Widget.create().id)
    println("${Delegated().speak()} ${Delegated().loud()} ${Triangle.label()} ${Triangle.sides}")
    println("${Member().hello()} ${Member().other()}")
    val op = Op { it * 3 }
    println("${op.run(2)} ${op.twice(2)}")
    println(Planet.entries.map { it.loud() })
    val sp: Speaker = Planet.MARS
    println(when (sp) { is Planet -> "planet ${sp.ordinal}"; else -> "other" })
    val (q, rem) = 17 divmod 5
    println("$q $rem")
    println(Outer("O").Inner("I").tags())

    println("== names / elvis return / when")
    println(`name with spaces`() + " " + π)
    println("${firstOrReturn(emptyList())} ${firstOrReturn(listOf(9))}")
    println((0..22 step 3).map(::word))
    println("${"inner ${"nested ${1 + 1}"}"} ${LONG_TEXT.length} ${LONG_TEXT.substring(LONG_TEXT.length - 9)}")
    var i = 0
    loop@ while (true) { when { i > 5 -> break@loop; i % 2 == 0 -> { i += 3; continue@loop } }; i++ }
    println(i)

    println("== Duration")
    println("${1500.milliseconds} ${2.seconds + 250.milliseconds} ${90.seconds} ${90.seconds.inWholeMinutes} ${1.5.minutes}")
    println("${1234567.microseconds} ${Duration.ZERO} ${Duration.INFINITE} ${(-3).seconds} ${3.seconds.inWholeMilliseconds}")
    println(Duration.parse("1h 30m").inWholeMinutes.toString() + " " + Duration.parseIsoString("PT2M3S"))
    println("done")
}
