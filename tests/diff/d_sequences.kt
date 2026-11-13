// sequence {} is a coroutine (suspend + yield): the same machinery as any suspend function.
fun fib() = sequence {
    var a = 0L
    var b = 1L
    while (true) {
        yield(a)
        val t = a + b
        a = b
        b = t
    }
}

fun primes() = sequence {
    var n = 2
    while (true) {
        if ((2 until n).none { n % it == 0 }) yield(n)
        n++
    }
}

fun tree(depth: Int, prefix: String): Sequence<String> = sequence {
    yield(prefix)
    if (depth > 0) {
        yieldAll(tree(depth - 1, prefix + "L"))
        yieldAll(tree(depth - 1, prefix + "R"))
    }
}

fun main() {
    println(fib().take(40).toList())
    println(primes().take(30).toList())
    println(tree(3, "*").toList())
    val it = iterator {
        for (i in 1..5) {
            yield(i * i)
            if (i == 3) yield(-1)
        }
    }
    val got = ArrayList<Int>()
    while (it.hasNext()) got.add(it.next())
    println(got)
    println(fib().map { it % 10 }.windowed(4).take(5).toList())
}
