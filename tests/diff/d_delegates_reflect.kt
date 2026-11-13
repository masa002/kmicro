// Delegated properties, KClass and typeOf, references, boxing, value classes, use. (A stack trace with a cause:
// d_known_stack_trace.kt; exitProcess: d_known_exit_process.kt)
import kotlin.properties.Delegates
import kotlin.reflect.typeOf

fun err(label: String, block: () -> Any?) {
    val r = runCatching(block)
    val e = r.exceptionOrNull()
    println("$label: " + if (e == null) "ok ${r.getOrNull()}" else "${e::class.simpleName}: ${e.message}")
}

class Config(map: Map<String, Any?>) {
    val name: String by map
    val port: Int by map
}

class Observed {
    val log = mutableListOf<String>()
    var temp: Int by Delegates.observable(20) { p, old, new -> log.add("${p.name}:$old->$new") }
    var limited: Int by Delegates.vetoable(0) { _, _, new -> new >= 0 }
    var late: String by Delegates.notNull()
}

data class Pt(val x: Int, val y: Int)
value class Meters(val v: Int) { operator fun plus(o: Meters) = Meters(v + o.v) }

class Res(val name: String, val log: MutableList<String>) : AutoCloseable {
    override fun close() { log.add("close $name") }
}

fun twice(f: (Int) -> Int) = f(f(1))
fun inc(x: Int) = x + 1

fun main() {
    val c = Config(mapOf("name" to "dev", "port" to 8080))
    println("by map: ${c.name} ${c.port}")
    err("by map missing") { Config(mapOf("name" to "x")).port }
    val o = Observed(); o.temp = 25; o.temp = 30; o.limited = 5; o.limited = -1
    println("observable: ${o.log} vetoable: ${o.limited}")
    err("notNull") { o.late }
    o.late = "set"; println("notNull set: ${o.late}")
    // reflection that needs no full kotlin-reflect
    println("class: ${Pt::class.simpleName} ${Pt::class.qualifiedName} ${Pt(1, 2)::class == Pt::class} ${Pt::class.isInstance(Pt(1, 1))} ${String::class.simpleName} ${IntArray::class.simpleName} ${listOf(1)::class.simpleName}")
    println("typeOf: ${typeOf<Map<String, List<Int?>>>()} ${typeOf<Pt?>()} ${typeOf<Array<out Number>>()}")
    println("references: ${Pt::x.name} ${Pt::x.get(Pt(7, 8))} ${::inc.name} ${twice(::inc)} ${listOf(1, 2).map(::inc)} ${::main.name} ${String::length.get("four")}")
    // boxing identity and equality
    val a: Int? = 127; val b: Int? = 127; val big1: Any = 1000; val big2: Any = 1000
    println("boxing: ${a === b} ${big1 == big2} ${(1000 as Any).hashCode()} ${(listOf(1000)[0] as Any) == 1000}")
    // value class
    val m = Meters(3) + Meters(4); println("value class: $m ${m.v} ${listOf(Meters(1), Meters(2))} ${m == Meters(7)}")
    // use / AutoCloseable
    val log = mutableListOf<String>()
    Res("a", log).use { log.add("body ${it.name}") }
    err("use with throw") { Res("b", log).use { error("inside use") } }
    println("use: $log")
    println("done")
}
