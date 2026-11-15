// Copyright 2026 the kmicro authors (NOTICE).
// SPDX-License-Identifier: Apache-2.0
@file:OptIn(kotlin.experimental.ExperimentalNativeApi::class, kotlinx.cinterop.ExperimentalForeignApi::class)

import kotlin.native.CName
import kotlinx.cinterop.ByteVar
import kotlinx.cinterop.allocArray
import kotlinx.cinterop.memScoped
import kotlinx.cinterop.toKString
import platform.posix.printf
import platform.posix.snprintf

// printf through platform.posix: newlib's stdio, the same stream as C's printf (main.c).
@CName("k_printf")
fun kPrintf() {
    val n = printf("printf from Kotlin says %d\n", 42)
    println("printf returned $n")
}

// The conversions of newlib-nano's printf (docs/kotlin-support.md, platform.posix): the integer ones of 32 bits,
// characters and strings. The floating-point ones print nothing unless the link has _printf_float (float.c, the
// test stdio_float), and there is no `ll` length: a Long goes through toString().
@CName("k_formats")
fun kFormats() = memScoped {
    val buf = allocArray<ByteVar>(80)
    snprintf(buf, 80u, "%5d|%-5d|%05d|%x|%X|%o|%c|%s|%u|%ld|%%", 42, -42, 42, 255, 255, 8, 'A'.code, "str",
             3000000000u, 7)
    println("integers: [${buf.toKString()}]")
    snprintf(buf, 80u, "%.2f V, %e, %g", 3.14159, 1234.5, 0.0001)
    println("floating point: [${buf.toKString()}]")
    snprintf(buf, 80u, "%lld ms", 5000000000L)
    println("a Long with %lld: [${buf.toKString()}]")
    snprintf(buf, 80u, "%s ms", 5000000000L.toString())
    println("a Long with %s: [${buf.toKString()}]")
}
