// Copyright 2026 the kmicro authors (NOTICE).
// SPDX-License-Identifier: Apache-2.0
package isr

import kotlin.concurrent.Volatile

// A handler may read array elements while the main code copies inside the array or fills it (copyInto, and with it
// ArrayList.removeAt and add(0, x); fill). Each element it reads must be a value some store put there, never some
// bytes of the old value and some of the new one: for a reference that would be a pointer to nowhere.

val north = Box(3000001)
val gap = Array(40) { Box(0) }      // about 500 bytes between the two boxes: their addresses differ in two bytes
val south = Box(3000002)
val ring = arrayOf<Box?>(north, south, north, south, north, south, north, south)
val flags = arrayOf<Box?>(north, north, north, north, north, north, north, north)

const val LOW = 0x11111111          // every byte differs between the two values
const val HIGH = 0x6EEEEEEE
val numbers = intArrayOf(LOW, HIGH, LOW, HIGH, LOW, HIGH, LOW, HIGH)
val levels = intArrayOf(LOW, LOW, LOW, LOW, LOW, LOW, LOW, LOW)

@Volatile var torn = 0

fun copySetup(): Int = gap.size + ring.size + flags.size + numbers.size + levels.size

// in the handler
fun copyRead(): Int {
    for (i in 0 until 8) {
        val a = ring[i]
        val b = flags[i]
        if (a !== north && a !== south) torn++
        if (b !== north && b !== south) torn++
        if (numbers[i] != LOW && numbers[i] != HIGH) torn++
        if (levels[i] != LOW && levels[i] != HIGH) torn++
    }
    return torn
}

// in main; n is the arrays' size, given by C so that no copy has a constant length
fun copyRotate(rounds: Int, n: Int): Int {
    repeat(rounds) { round ->
        if (round % 2 == 0) {                   // down: the destination is below the source
            val box = ring[0]
            ring.copyInto(ring, 0, 1, n)
            ring[n - 1] = box
            val number = numbers[0]
            numbers.copyInto(numbers, 0, 1, n)
            numbers[n - 1] = number
        } else {                                // up: copied backwards
            val box = ring[n - 1]
            ring.copyInto(ring, 1, 0, n - 1)
            ring[0] = box
            val number = numbers[n - 1]
            numbers.copyInto(numbers, 1, 0, n - 1)
            numbers[0] = number
        }
        flags.fill(if (round % 2 == 0) south else north, 0, n)
        levels.fill(if (round % 2 == 0) HIGH else LOW, 0, n)
    }
    return torn
}
