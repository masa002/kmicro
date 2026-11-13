// Language probe 2: constructors, properties, lateinit, delegated properties, class delegation.
import kotlin.properties.Delegates
import kotlin.properties.PropertyDelegateProvider
import kotlin.properties.ReadOnlyProperty
import kotlin.properties.ReadWriteProperty
import kotlin.reflect.KProperty

class Person(val name: String, var age: Int = 30, val tags: List<String> = emptyList()) {
    var nick: String = name.lowercase()
        set(value) { field = value.trim(); changes++ }
        get() = "~$field"
    var changes = 0
        private set
    val isAdult: Boolean get() = age >= 18
    var counter: Int = 0
        set(v) { require(v >= 0) { "counter must be >= 0, was $v" }; field = v }

    constructor(name: String, birthYear: Int, now: Int) : this(name, now - birthYear) {
        println("secondary ctor for $name")
    }

    init { println("init $name age=$age") }
}

class Logger {
    var lines = mutableListOf<String>()
}

class Holder {
    lateinit var text: String
    lateinit var logger: Logger
    fun isTextReady() = this::text.isInitialized
}

lateinit var topLevelLate: String

fun sum(vararg xs: Int): Int = xs.sum()
fun joinAll(sep: String = ",", vararg parts: String, suffix: String = "!"): String = parts.joinToString(sep) + suffix
fun <T> countOf(vararg items: T): Int = items.size

class Lazy2 {
    val heavy: String by lazy { println("computing heavy"); "HEAVY" }
    val pub: Int by lazy(LazyThreadSafetyMode.PUBLICATION) { 41 + 1 }
    val none: Int by lazy(LazyThreadSafetyMode.NONE) { 7 }
}

val topLazy: List<Int> by lazy { println("topLazy init"); listOf(1, 2, 3) }

class Observed {
    var events = mutableListOf<String>()
    var value: Int by Delegates.observable(0) { prop, old, new -> events += "${prop.name}:$old->$new" }
    var positive: Int by Delegates.vetoable(1) { _, _, new -> new > 0 }
    var late: String by Delegates.notNull()
}

class MapBacked(map: Map<String, Any?>) {
    val name: String by map
    val age: Int by map
}

class MutableMapBacked(val map: MutableMap<String, Any?>) {
    var color: String by map
}

class Upper : ReadWriteProperty<Any?, String> {
    private var v = ""
    override fun getValue(thisRef: Any?, property: KProperty<*>): String = v
    override fun setValue(thisRef: Any?, property: KProperty<*>, value: String) { v = value.uppercase() }
}

fun constant(x: Int) = ReadOnlyProperty<Any?, Int> { _, p -> x + p.name.length }

class Plain {
    operator fun getValue(thisRef: Any?, property: KProperty<*>): String = "plain(${property.name})"
}

class Checked(private val min: Int) {
    operator fun provideDelegate(thisRef: Any?, prop: KProperty<*>): ReadWriteProperty<Any?, Int> {
        println("provideDelegate for ${prop.name}")
        return object : ReadWriteProperty<Any?, Int> {
            var v = min
            override fun getValue(thisRef: Any?, property: KProperty<*>) = v
            override fun setValue(thisRef: Any?, property: KProperty<*>, value: Int) { v = maxOf(min, value) }
        }
    }
}

val providerFn = PropertyDelegateProvider<Any?, ReadOnlyProperty<Any?, String>> { _, prop ->
    ReadOnlyProperty { _, _ -> "provided-" + prop.name }
}

class Delegating {
    var shout: String by Upper()
    val seven by constant(2)
    val plain by Plain()
    var bounded by Checked(10)
    val fromProvider by providerFn
}

class Wrapper {
    var inner = 5
    var alias: Int by this::inner
}

interface Sink {
    fun write(s: String)
    val count: Int
    fun flush(): String = "flush-default"
}

class ListSink : Sink {
    val items = mutableListOf<String>()
    override fun write(s: String) { items += s }
    override val count get() = items.size
    override fun flush() = "flushed ${items.size}"
}

class Tee(private val inner: Sink) : Sink by inner {
    override fun write(s: String) { inner.write("[$s]") }
}

class CountingList<T>(private val impl: MutableList<T> = ArrayList()) : MutableList<T> by impl {
    var adds = 0
    override fun add(element: T): Boolean { adds++; return impl.add(element) }
}

fun main() {
    println("== constructors")
    val a = Person("Ann")
    val b = Person("Bob", age = 12)
    val c = Person(tags = listOf("x"), name = "Cy")
    val d = Person("Dee", 1990, 2026)
    println("${a.age} ${b.age} ${c.tags} ${d.age}")
    a.nick = "  Annie  "
    a.nick = "A"
    println("${a.nick} ${a.changes} ${a.isAdult} ${b.isAdult}")
    println(runCatching { a.counter = -1 }.exceptionOrNull()?.message)
    println(sum() + sum(1) + sum(1, 2, 3))
    val arr = intArrayOf(4, 5, 6)
    println(sum(*arr) + sum(1, *arr, 10))
    println(joinAll(parts = arrayOf("a", "b")))
    println(joinAll("-", "x", "y", "z", suffix = "?"))
    val sarr = arrayOf("p", "q")
    println(joinAll("+", *sarr, "r"))
    println(countOf(1, "two", 3.0, null))

    println("== lateinit")
    val h = Holder()
    println(h.isTextReady())
    val e = runCatching { h.text.length }.exceptionOrNull()
    println("${e?.let { it::class.simpleName }}: ${e?.message}")
    h.text = "ready"
    println("${h.isTextReady()} ${h.text}")
    val e2 = runCatching { topLevelLate }.exceptionOrNull()
    println("${e2?.let { it::class.simpleName }}: ${e2?.message}")
    topLevelLate = "top"
    println(topLevelLate)
    println(runCatching { h.logger.lines.size }.exceptionOrNull()?.message)

    println("== lazy")
    val l = Lazy2()
    println("created")
    println(l.heavy + l.heavy + " " + l.pub + " " + l.none)
    println("before topLazy")
    println(topLazy.sum() + topLazy.size)
    val lz = lazy { 5 }
    println("${lz.isInitialized()} ${lz.value} ${lz.isInitialized()} $lz")

    println("== observable/vetoable/notNull")
    val ob = Observed()
    ob.value = 3
    ob.value = 8
    println(ob.events)
    ob.positive = -5
    println(ob.positive)
    ob.positive = 9
    println(ob.positive)
    val nn = runCatching { ob.late }.exceptionOrNull()
    println("${nn?.let { it::class.simpleName }}: ${nn?.message}")
    ob.late = "set"
    println(ob.late)

    println("== map delegation")
    val mb = MapBacked(mapOf("name" to "Map", "age" to 3))
    println("${mb.name} ${mb.age}")
    val missing = runCatching { MapBacked(mapOf("name" to "x")).age }.exceptionOrNull()
    println("${missing?.let { it::class.simpleName }}: ${missing?.message}")
    val mm = MutableMapBacked(mutableMapOf("color" to "red"))
    mm.color = "blue"
    println("${mm.color} ${mm.map}")

    println("== custom delegates")
    val dg = Delegating()
    dg.shout = "hello"
    println("${dg.shout} ${dg.seven} ${dg.plain} ${dg.bounded}")
    dg.bounded = 3
    println(dg.bounded)
    dg.bounded = 30
    println(dg.bounded)
    println(dg.fromProvider)
    val w = Wrapper()
    w.alias = 42
    println("${w.inner} ${w.alias}")

    println("== class delegation")
    val ls = ListSink()
    val t = Tee(ls)
    t.write("a"); t.write("b")
    println("${ls.items} ${t.count} ${t.flush()}")
    val cl = CountingList<Int>()
    cl.add(1); cl.add(2); cl.addAll(listOf(3, 4))
    println("${cl.adds} ${cl.size} ${cl.toList()} ${cl.contains(3)} ${cl.indexOf(4)}")
    println("done")
}
