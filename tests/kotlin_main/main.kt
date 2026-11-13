package app

import kotlin.time.Duration
import kotlin.time.measureTime

// A Kotlin-only program: kbuild gives this main the C name kmicro_kotlin_main, which targets/common/kotlin_main.c
// calls. It also parses a number on the default 16 KB heap, and times a loop with the clock the QEMU start code gives.
fun main() {
    println("main in package app")
    val d = "3.14".toDouble()
    println("parsed $d, twice ${d * 2}")
    val t = measureTime { repeat(1000) { } }
    println("measureTime positive: ${t > Duration.ZERO}")
}
