// kotlin.random and kotlin.time. A seeded Random gives the same numbers on every platform. Random.Default, the
// monotonic clock and the system clock give different values on every run, so only their properties are printed.
@file:OptIn(kotlin.time.ExperimentalTime::class)

import kotlin.random.Random
import kotlin.time.Clock
import kotlin.time.Duration
import kotlin.time.TimeSource
import kotlin.time.measureTime

fun main() {
    val r = Random(42)
    println("Random(42).nextInt(100): " + List(5) { r.nextInt(100) })
    println("Random(42).nextInt(): " + Random(42).let { g -> List(4) { g.nextInt() } })
    println("Random(7).nextLong(): " + Random(7).let { g -> List(3) { g.nextLong() } })
    println("Random(7).nextDouble(): " + Random(7).let { g -> List(3) { g.nextDouble() } })
    println("Random(9).nextBoolean(): " + Random(9).let { g -> List(6) { g.nextBoolean() } })
    println("Random(5).nextInt(10, 20): " + Random(5).nextInt(10, 20))
    println("Random(1).nextBytes(8): " + Random(1).nextBytes(8).toList())
    println("shuffled(Random(7)): " + (1..10).toList().shuffled(Random(7)))
    val m = (1..10).toMutableList()
    m.shuffle(Random(3))
    println("shuffle(Random(3)): $m")
    println("(1..6).random() in 1..6: " + ((1..6).random() in 1..6))
    println("Random.nextInt(10) in 0..9: " + (Random.nextInt(10) in 0..9))
    println("shuffled().sorted(): " + listOf(3, 1, 2).shuffled().sorted())
    println("measureTime >= ZERO: " + (measureTime { repeat(1000) { } } >= Duration.ZERO))
    val a = TimeSource.Monotonic.markNow()
    val b = TimeSource.Monotonic.markNow()
    println("marks ordered: " + (b >= a))
    println("elapsedNow >= ZERO: " + (a.elapsedNow() >= Duration.ZERO))
    println("Clock.System.now() after 2020: " + (Clock.System.now().epochSeconds > 1577836800L))
}
