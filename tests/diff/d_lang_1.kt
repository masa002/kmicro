// Language probe 1: classes, interfaces, data classes, enums, objects, nested/inner/local/anonymous classes.

interface Shape {
    val name: String get() = "shape"
    fun area(): Double
    fun describe(): String = "$name area=${area()}"
}

abstract class Base(val id: Int) : Shape {
    abstract val kind: String
    open fun tag(): String = "base#$id"
    override fun toString(): String = "Base($id,$kind)"
}

open class Rect(id: Int, val w: Double, val h: Double) : Base(id) {
    override val kind = "rect"
    override val name: String get() = "rect"
    override fun area() = w * h
    override fun tag(): String = "rect:" + super.tag()
}

class Square(id: Int, s: Double) : Rect(id, s, s) {
    override val kind = "square"
    override fun tag(): String = "sq/" + super.tag()
}

sealed class Expr {
    data class Num(val v: Int) : Expr()
    data class Add(val a: Expr, val b: Expr) : Expr()
    data class Mul(val a: Expr, val b: Expr) : Expr()
    object Zero : Expr() { override fun toString() = "Zero" }
}

fun eval(e: Expr): Int = when (e) {
    is Expr.Num -> e.v
    is Expr.Add -> eval(e.a) + eval(e.b)
    is Expr.Mul -> eval(e.a) * eval(e.b)
    Expr.Zero -> 0
}

sealed interface Event
data class Click(val x: Int, val y: Int) : Event
data class Key(val code: Char) : Event
data object Tick : Event
enum class Sys : Event { BOOT, HALT }

fun handle(e: Event): String = when (e) {
    is Click -> "click ${e.x},${e.y}"
    is Key -> "key ${e.code}"
    Tick -> "tick"
    Sys.BOOT -> "boot"
    Sys.HALT -> "halt"
}

data class Point(val x: Int, val y: Int = 0) {
    var label: String = "none"           // not part of equals/hashCode/toString
    operator fun plus(o: Point) = Point(x + o.x, y + o.y)
}

data class Mixed(val b: Byte, val s: Short, val l: Long, val f: Float, val d: Double, val c: Char, val z: Boolean,
                 val str: String?, val arr: IntArray, val list: List<Int>)

enum class Color(val rgb: Int) {
    RED(0xFF0000), GREEN(0x00FF00), BLUE(0x0000FF);
    fun hex(): String = "#" + rgb.toString(16).padStart(6, '0')
    companion object {
        fun parse(s: String): Color? = entries.firstOrNull { it.name.equals(s, ignoreCase = true) }
    }
}

enum class Op {
    PLUS { override fun apply(a: Int, b: Int) = a + b },
    TIMES { override fun apply(a: Int, b: Int) = a * b };
    abstract fun apply(a: Int, b: Int): Int
}

enum class Level : Comparable<Level> { LOW, MID, HIGH }

object Counter {
    private var n = 0
    const val LIMIT = 3
    val created: String
    init {
        println("Counter init")
        created = "counter-created"
    }
    fun next(): Int = ++n
}

class Machine private constructor(val name: String) {
    companion object Factory {
        const val PREFIX = "m-"
        private var made = 0
        init { println("Machine.Factory init") }
        fun create(n: String): Machine { made++; return Machine(PREFIX + n) }
        val count get() = made
    }
}

class Outer(val v: Int) {
    class Nested { fun hi() = "nested" }
    inner class Inner(val w: Int) {
        fun sum() = v + w
        fun outerRef() = this@Outer.v
    }
}

interface Greeter { fun greet(who: String): String }

fun makeGreeter(prefix: String): Greeter {
    var calls = 0
    val g = object : Greeter {
        override fun greet(who: String): String { calls++; return "$prefix $who ($calls)" }
    }
    g.greet("warm")
    return g
}

fun localClass(): String {
    var total = 0
    class Acc(val step: Int) { fun add() { total += step } }
    val a = Acc(5)
    a.add(); a.add()
    data class Pair2(val a: Int, val b: String)
    val p = Pair2(1, "x")
    return "total=$total pair=$p"
}

open class InitOrder(val a: String) {
    init { println("InitOrder.init1 a=$a") }
    val b = "b-of-$a".also { println("InitOrder.b") }
    init { println("InitOrder.init2 b=$b") }
    open val c: String = "c"
}

class InitChild(x: String) : InitOrder(x.uppercase()) {
    init { println("InitChild.init") }
    override val c: String = "child-c"
}

fun main() {
    println("== inheritance")
    val shapes: List<Shape> = listOf(Rect(1, 2.0, 3.0), Square(2, 4.0))
    for (s in shapes) println(s.describe() + " " + (s as Base).tag() + " " + s)
    val anon = object : Shape { override fun area() = 1.5 }
    println(anon.describe())

    println("== sealed")
    println(eval(Expr.Add(Expr.Num(2), Expr.Mul(Expr.Num(3), Expr.Num(4)))))
    println(Expr.Add(Expr.Num(1), Expr.Zero))
    println(listOf(Click(1, 2), Key('k'), Tick, Sys.BOOT, Sys.HALT).map(::handle))
    println("Tick=$Tick tick hash equal=${Tick.hashCode() == Tick.hashCode()} eq=${Tick == Tick}")

    println("== data class")
    val p = Point(1, 2)
    val q = p.copy(y = 5)
    p.label = "lab"
    println("$p $q ${p == Point(1, 2)} ${p == q} ${p.hashCode() == Point(1, 2).hashCode()} ${p.hashCode()}")
    println("${p.component1()} ${p.component2()} ${Point(7)}")
    val (x, y) = q
    println("destructured $x $y")
    val pts = listOf(Point(1, 1), Point(2, 4), Point(3, 9))
    for ((a, b) in pts) print("$a:$b ")
    println()
    println(pts.map { (a, b) -> a * 10 + b })
    println(pts.map { (_, b) -> b })
    val m = mapOf("one" to 1, "two" to 2)
    for ((k, v) in m) print("$k=$v ")
    println()
    m.forEach { (k, v) -> print("[$k $v]") }
    println()
    val mixed = Mixed(1, 2, 3L, 1.5f, 2.25, 'c', true, null, intArrayOf(1), listOf(1, 2))
    println(mixed.toString().substringBefore("arr="))
    println(mixed.hashCode() == mixed.copy().hashCode())
    println(mixed == mixed.copy())
    println(Mixed(1, 2, 3L, 1.5f, 2.25, 'c', true, "s", intArrayOf(1), listOf(1, 2)).hashCode() != 0)
    println("pair ${Pair(1, "a")} triple ${Triple(1, 2.0, 'c')}")
    val (f, s2) = Pair("first", 2)
    println("$f $s2")
    println(p + q)

    println("== enum")
    println(Color.entries)
    println(Color.values().joinToString())
    println(Color.valueOf("GREEN").hex() + " " + Color.GREEN.ordinal + " " + Color.GREEN.name)
    println("${Color.parse("blue")} ${Color.parse("pink")}")
    val bad = runCatching { Color.valueOf("PINK") }
    println("valueOf fail: ${bad.exceptionOrNull()?.let { it::class.simpleName }} ${bad.exceptionOrNull()?.message}")
    println(Op.entries.map { it.apply(6, 7) })
    println(Op.PLUS.javaClassName())
    println(Level.HIGH > Level.LOW)
    println(Level.MID.compareTo(Level.HIGH))
    println(enumValues<Level>().toList() + enumValueOf<Level>("MID"))
    val c = Color.BLUE
    println(when (c) { Color.RED -> "r"; Color.GREEN -> "g"; Color.BLUE -> "b" })
    println(Color.entries.associateWith { it.rgb }.entries.joinToString())
    println(Color.RED.hashCode() == Color.RED.hashCode())
    println(Color.entries.sortedDescending())

    println("== objects")
    println("before Counter")
    println(Counter.LIMIT)
    println(Counter.next() + Counter.next())
    println(Counter.created)
    println("before Machine")
    println(Machine.PREFIX)
    val mm = Machine.create("a")
    Machine.Factory.create("b")
    println("${mm.name} ${Machine.count}")
    println(Counter::class.simpleName + " " + Machine.Factory::class.simpleName)

    println("== nested/inner/local/anonymous")
    println(Outer.Nested().hi())
    val o = Outer(10)
    val i = o.Inner(5)
    println("${i.sum()} ${i.outerRef()}")
    val g = makeGreeter("hi")
    println(g.greet("a"))
    println(g.greet("b"))
    println(localClass())
    var captured = 0
    val runner = object : Runnable2 {
        override fun run() { captured += 10 }
    }
    runner.run(); runner.run()
    println("captured=$captured")
    val adHoc = object {
        val a = 1
        val b = "two"
        override fun toString() = "adHoc($a,$b)"
    }
    println("${adHoc.a} ${adHoc.b} $adHoc")

    println("== init order")
    val ic = InitChild("x")
    println("${ic.a} ${ic.b} ${ic.c}")
    println("done")
}

interface Runnable2 { fun run() }

fun Op.javaClassName(): String = "op " + this::class.simpleName + " " + this.name
