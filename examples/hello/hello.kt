package hello

// C calls this as `int32_t hello(int32_t times)` (hello.h): kbuild.py --c-api hello.h --package hello gives the
// Kotlin function hello.hello that C name.
fun hello(times: Int): Int {
    val names = List(times) { "Kotlin #${it + 1}" }
    println("Hello from ${names.joinToString()} on a bare Cortex-M4")
    return names.size
}
