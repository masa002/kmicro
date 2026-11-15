// Copyright 2026 the kmicro authors (NOTICE).
// SPDX-License-Identifier: Apache-2.0
package app

import kotlin.time.Duration
import kotlin.time.measureTime

// A member function named main is no entry point: kbuild must not take it for a second main.
class Menu {
    fun main() {
        println("main of Menu")
    }
}

// A Kotlin-only program: kbuild gives this main the C name kmicro_kotlin_main, which targets/common/kotlin_main.c
// calls. It also parses a number on the default 16 KB heap, and times a loop with the clock the QEMU start code gives.
fun main() {
    println("main in package app")
    Menu().main()
    val d = "3.14".toDouble()
    println("parsed $d, twice ${d * 2}")
    val t = measureTime { repeat(1000) { } }
    println("measureTime positive: ${t > Duration.ZERO}")
}
