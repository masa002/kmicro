// Copyright 2026 the kmicro authors (NOTICE).
// SPDX-License-Identifier: Apache-2.0
@file:OptIn(kotlinx.cinterop.ExperimentalForeignApi::class)
package isr

import kotlinx.cinterop.ByteVar
import kotlinx.cinterop.IntVar
import kotlinx.cinterop.alloc
import kotlinx.cinterop.allocArray
import kotlinx.cinterop.free
import kotlinx.cinterop.get
import kotlinx.cinterop.nativeHeap
import kotlinx.cinterop.pointed
import kotlinx.cinterop.set
import kotlinx.cinterop.toCPointer
import kotlinx.cinterop.toLong
import kotlinx.cinterop.value
import kotlin.random.Random
import kotlin.time.Duration.Companion.milliseconds

// Objects of the standard library that are created on first use: the NativePtr companion (every conversion between a
// pointer and an address, and nativeHeap), the companions of the cinterop variable types, the unsigned range classes,
// Random.Default, the Duration units. This code refers to them, so kt_init_all() (kbuild --init-all) creates them at
// boot, and the handler may be the first code to make each of these calls. Returns the checks that held: 5.
fun libraryInHandler(address: Int, n: Int): Int {
    var ok = 0
    val p = nativeHeap.alloc<IntVar>()
    val bytes = nativeHeap.allocArray<ByteVar>(8)
    p.value = n
    bytes[7] = 3
    if (p.value == n && bytes[7].toInt() == 3) ok += 1
    nativeHeap.free(bytes)
    nativeHeap.free(p)
    val word = address.toLong().toCPointer<IntVar>()            // the address of a C variable that holds 1234
    if (word != null && word.pointed.value == 1234 && word.toLong() == address.toLong()) ok += 1
    val adc = (n * 1000).toUInt()
    if ((adc in 1000u..3000u) == (n in 1..3)) ok += 1
    if (Random.nextInt(10) in 0..9) ok += 1
    if ((n.milliseconds < 3.milliseconds) == (n < 3)) ok += 1
    return ok
}
