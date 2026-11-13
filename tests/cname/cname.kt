@file:OptIn(kotlin.experimental.ExperimentalNativeApi::class)

import kotlin.native.CName

// C calls these by their @CName names (main.c), with plain C types: kn.build gives each Kotlin function
// its C name.

@CName("k_add")
fun add(a: Int, b: Int): Int = a + b

@CName("k_scale")
fun scale(x: Double, f: Float): Double = x * f

@CName("k_is_even")
fun isEven(n: Long): Boolean = n % 2L == 0L

@CName("k_low_byte")
fun lowByte(n: UInt): UByte = (n and 0xFFu).toUByte()

@CName("k_note")
fun note(n: Int) {
    println("Kotlin note($n)")
}
