// Language probe 3: generics, reified types, value classes, typealias, reflection-lite, default Any members.
import kotlin.reflect.KClass
import kotlin.reflect.typeOf

interface Source<out T> { fun next(): T }
interface Consumer<in T> { fun take(t: T): String }

class Const<T>(private val v: T) : Source<T> { override fun next() = v }
object AnyPrinter : Consumer<Any?> { override fun take(t: Any?) = "took $t" }

fun copyAll(from: Array<out Number>, to: Array<in Number>) { for (i in from.indices) to[i] = from[i] }

fun describeList(l: List<*>): String = "size=${l.size} first=${l.firstOrNull()}"

fun <T : Comparable<T>> maxOf3(a: T, b: T, c: T): T = maxOf(a, maxOf(b, c))

fun <T> joinIfBoth(a: T, b: T): String where T : CharSequence, T : Comparable<T> =
    if (a < b) "$a<$b" else "$b<=$a"

inline fun <reified T> isA(x: Any?): Boolean = x is T
inline fun <reified T : Any> nameOf(): String? = T::class.simpleName
inline fun <reified T> filterType(xs: List<Any?>): List<T> = xs.filterIsInstance<T>()
inline fun <reified T> typeName(): String = typeOf<T>().toString()
inline fun <reified T : Enum<T>> enumNames(): List<String> = enumValues<T>().map { it.name }

typealias Handler = (Int) -> String
typealias StrMap<V> = Map<String, V>

class Box<T>(var item: T) {
    fun <R> map(f: (T) -> R): Box<R> = Box(f(item))
    override fun toString() = "Box($item)"
}

value class Meters(val v: Double) {
    operator fun plus(o: Meters) = Meters(v + o.v)
    val km get() = v / 1000
    override fun toString(): String = "${v}m"
}

value class UserId(val raw: Int) : Comparable<UserId> {
    init { require(raw >= 0) { "negative id $raw" } }
    override fun compareTo(other: UserId) = raw.compareTo(other.raw)
}

value class Name(val s: String)

interface Tagged { val tag: String }
value class Tag(val t: String) : Tagged { override val tag get() = "#$t" }

enum class Dir { N, E, S, W }

class Plain(val x: Int)
data class DC(val x: Int)
interface I1
interface I2 : I1
open class P : I2
class Q : P()

fun main() {
    println("== variance")
    val src: Source<Number> = Const(42)
    println(src.next())
    val cons: Consumer<String> = AnyPrinter
    println(cons.take("s"))
    val from = arrayOf<Number>(1, 2.5, 3L)
    val to = arrayOfNulls<Any>(3)
    copyAll(from, to)
    println(to.toList())
    println(describeList(listOf("a", 1, null)))
    val star: Box<*> = Box(5)
    println(star.item)
    println(maxOf3(3, 9, 4) + maxOf3("b", "c", "a").length)
    println(joinIfBoth("x", "a"))
    println(Box(3).map { it * 1.5 }.map { "v=$it" })

    println("== reified")
    println("${isA<String>("s")} ${isA<String>(1)} ${isA<Int?>(null)} ${isA<List<*>>(listOf(1))} ${isA<Comparable<*>>(3)}")
    println("${nameOf<String>()} ${nameOf<Box<Int>>()} ${nameOf<Dir>()}")
    println(filterType<Int>(listOf(1, "a", 2, null, 3.0)))
    println(filterType<String>(listOf(1, "a", 2, null, "b")))
    println(enumNames<Dir>())

    println("== typeOf")
    println(typeName<Int>())
    println(typeName<String?>())
    println(typeName<List<Int>>())
    println(typeName<Map<String, List<Int?>>>())
    println(typeName<Box<*>>())
    println(typeName<Array<out Number>>())
    println(typeName<IntArray>())
    println(typeName<Handler>())
    println(typeOf<Int>() == typeOf<Int>())
    println(typeOf<List<Int>>().arguments.map { it.toString() })
    println(typeOf<String?>().isMarkedNullable)
    println(typeOf<Dir>().classifier == Dir::class)

    println("== typealias")
    val h: Handler = { "h$it" }
    println(h(7))
    val sm: StrMap<Int> = mapOf("a" to 1)
    println(sm)

    println("== value classes")
    val m = Meters(1500.0) + Meters(250.0)
    println("$m ${m.km} ${m.v}")
    val ids = listOf(UserId(3), UserId(1), UserId(2))
    println(ids.sorted().map { it.raw })
    println(ids.maxOrNull()?.raw)
    val maybe: UserId? = ids.firstOrNull { it.raw > 2 }
    println(maybe?.raw)
    val none: UserId? = ids.firstOrNull { it.raw > 5 }
    println(none?.raw ?: -1)
    println(runCatching { UserId(-1) }.exceptionOrNull()?.message)
    val names = setOf(Name("a"), Name("b"), Name("a"))
    println(names.size)
    println(Name("x") == Name("x"))
    println(Name("x").hashCode() == "x".hashCode())
    println(Name("q"))
    val tg: Tagged = Tag("v")
    println(tg.tag + " " + (tg is Tag))
    val anyM: Any = Meters(1.0)
    println("$anyM ${anyM is Meters}")
    val mapV = mapOf(UserId(1) to Meters(2.0))
    println(mapV[UserId(1)])
    val arr = Array(2) { Meters(it.toDouble()) }
    println(arr.joinToString())

    println("== class names")
    println("${Plain::class.simpleName} ${Plain::class.qualifiedName} ${DC::class.simpleName}")
    println("${String::class.simpleName} ${Int::class.qualifiedName} ${List::class.simpleName} ${IntArray::class.simpleName}")
    println("${Dir.N::class.simpleName} ${Box::class.qualifiedName} ${Meters::class.simpleName}")
    val k1: KClass<*> = Plain(1)::class
    println("${k1 == Plain::class} ${k1 == DC::class} ${Plain::class.hashCode() == Plain::class.hashCode()}")
    println(k1)
    println(Plain::class.isInstance(Plain(2)))
    println(listOf(1, "a", 2.0, 'c', 1L, true, null).map { it?.let { v -> v::class.simpleName } })
    val lambda = { x: Int -> x }
    println(lambda::class.simpleName != null)
    println(object {}::class.simpleName)

    println("== default Any members")
    val p1 = Plain(1)
    val s = p1.toString()
    println(s.substringBefore('@') + " has@=" + s.contains('@') + " hexOk=" + s.substringAfter('@').all { it in "0123456789abcdef" })
    println("${p1 == p1} ${p1 == Plain(1)} ${p1.hashCode() == p1.hashCode()} ${p1.equals(null)}")
    println(DC(1) == DC(1))
    val arrS = intArrayOf(1).toString()
    println(arrS.substringBefore('@'))
    println(Any().toString().substringBefore('@'))

    println("== is checks / erasure")
    val q: Any = Q()
    println("${q is I1} ${q is I2} ${q is P} ${q is Q} ${q is Plain}")
    val anyList: Any = listOf(1, 2)
    println("${anyList is List<*>} ${anyList is Collection<*>} ${anyList is MutableList<*>} ${anyList is Set<*>}")
    @Suppress("UNCHECKED_CAST")
    val forced = anyList as List<String>
    println(forced.size)
    println(runCatching { forced[0].length }.exceptionOrNull()?.let { it::class.simpleName })
    val fn: Any = { x: Int -> x + 1 }
    println("${fn is Function1<*, *>} ${fn is Function0<*>} ${fn is Function<*>}")
    println("done")
}
