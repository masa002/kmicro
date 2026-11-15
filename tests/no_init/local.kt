// Copyright 2026 the kmicro authors (NOTICE).
// SPDX-License-Identifier: Apache-2.0
import kotlin.native.concurrent.ThreadLocal

// main.c calls this program without kmicro_init(). Most Kotlin code would still run: globals initialise at their first
// use. A @ThreadLocal global needs the tables kmicro_init() fills, and the runtime says what is missing.
@ThreadLocal
val scratch = IntArray(4)

fun main() {
    println("the program ran without kmicro_init(): ${scratch.size}")
}
