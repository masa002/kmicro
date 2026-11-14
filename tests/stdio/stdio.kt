@file:OptIn(kotlin.experimental.ExperimentalNativeApi::class, kotlinx.cinterop.ExperimentalForeignApi::class)

import kotlin.native.CName
import platform.posix.printf

// printf through platform.posix: newlib's stdio, the same stream as C's printf (main.c).
@CName("k_printf")
fun kPrintf() {
    val n = printf("printf from Kotlin says %d\n", 42)
    println("printf returned $n")
}
