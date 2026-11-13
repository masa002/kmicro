class AppError(msg: String, val code: Int) : RuntimeException(msg)

fun risky(n: Int): Int {
    require(n >= 0) { "negative: $n" }
    check(n < 100) { "too big: $n" }
    if (n == 13) throw AppError("unlucky", 13)
    return 100 / (n - 7)
}

val lazyValue: Int by lazy { println("computing lazy"); 42 }

fun recurse(d: Int): Int = if (d == 0) throw AppError("deep", d) else recurse(d - 1) + 1

fun main() {
    for (n in listOf(1, -5, 150, 13, 7, 8)) {
        val r = runCatching { risky(n) }
        println("$n -> ${r.getOrNull()} ${r.exceptionOrNull()?.let { "${it::class.simpleName}: ${it.message}" }}")
    }
    var trace = ""
    try {
        try {
            trace += "a"
            throw AppError("inner", 1)
        } catch (e: IllegalStateException) {
            trace += "x"
        } finally {
            trace += "f"
        }
    } catch (e: AppError) {
        trace += "c${e.code}"
    }
    println(trace)
    val s: String? = listOf<String?>(null).first()
    println(runCatching { s!!.length }.exceptionOrNull()?.let { it::class.simpleName })
    println(runCatching { listOf(1)[5] }.exceptionOrNull()?.let { it::class.simpleName + ": " + it.message })
    println(runCatching { "12x".toInt() }.exceptionOrNull()?.let { it::class.simpleName + ": " + it.message })
    println(runCatching { (Any() as String).length }.exceptionOrNull()?.let { it::class.simpleName })
    println("12".toInt() + "-7".toInt() + "0x1F".removePrefix("0x").toInt(16))
    println(lazyValue + lazyValue)
    val e = AppError("with cause", 5)
    val wrapped = IllegalStateException("outer", e)
    println("${wrapped.message} / ${wrapped.cause?.message} / ${wrapped.cause is AppError}")
    println(e.toString())
    var depth = 0
    try { recurse(30) } catch (x: AppError) { depth = 30 }
    println("deep caught $depth")
}
