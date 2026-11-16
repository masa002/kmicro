// Copyright 2026 the kmicro authors (NOTICE).
// SPDX-License-Identifier: Apache-2.0
package isr

// A handler that classifies the characters it receives, as a line protocol does. The standard library answers for
// ASCII without its Unicode tables; a character above U+007F reads them. The tables are constants and their files
// have no first use (toolchain/retarget.py), so the handler may be the first code of the program to read them:
// this file has no global of its own, and the test does not call kt_init_all(). (Char.category and isTitleCase()
// are not here: they create the 30 CharCategory entries on first use, which a handler must not do.)

const val RECEIVED = "T=23,5°C Été Ω ٣ ǅ ß x7\tZ"

// What SysTick_Handler calls with the number of the tick, and the main code afterwards with the same numbers.
fun classify(n: Int): Int {
    val c = RECEIVED[n % RECEIVED.length]
    var bits = 0
    if (c.isLetter()) bits = bits or 1
    if (c.isDigit()) bits = bits or 2
    if (c.isLetterOrDigit()) bits = bits or 4
    if (c.isUpperCase()) bits = bits or 8
    if (c.isLowerCase()) bits = bits or 16
    if (c.isWhitespace()) bits = bits or 64
    if (c.uppercaseChar() != c) bits = bits or 128
    if (c.lowercaseChar() != c) bits = bits or 256
    if (c.titlecaseChar() != c) bits = bits or 512
    if (c.isDigit()) bits += c.digitToInt() shl 12
    return bits + (n and 3)
}
