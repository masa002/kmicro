// Initialization semantics: lazy top-level properties, objects, a failing initializer (accessed twice), companions.
object Registry {
    val names = mutableListOf<String>()
    init { names += "registry-init" }
    fun add(n: String) { names += n }
}

class Device(val id: Int) {
    companion object {
        var created = 0
        val first = Device(-1)
        init { println("companion init") }
    }
    init { created++ }
}

val greeting: String = run { println("greeting initialized"); "hello" }

fun failing(): Int = throw IllegalStateException("broken initializer")

object Broken {
    val value: Int = failing()
}

fun main() {
    println("start")
    println(greeting + " " + greeting)
    Registry.add("a")
    Registry.add("b")
    println(Registry.names)
    println(Device(1).id + Device(2).id)
    println("created=" + Device.created + " first=" + Device.first.id)
    for (attempt in 1..2) {
        val r = runCatching { Broken.value }
        val e = r.exceptionOrNull()
        println("attempt $attempt: ${e?.let { it::class.simpleName }} / ${e?.message} / cause=${e?.cause?.message}")
    }
    println("end")
}
