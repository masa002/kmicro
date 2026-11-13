// Duration.toString(unit, decimals): exact decimal digits, rounded half to even like printf("%.*f").

import kotlin.time.Duration
import kotlin.time.Duration.Companion.days
import kotlin.time.Duration.Companion.hours
import kotlin.time.Duration.Companion.microseconds
import kotlin.time.Duration.Companion.milliseconds
import kotlin.time.Duration.Companion.minutes
import kotlin.time.Duration.Companion.nanoseconds
import kotlin.time.Duration.Companion.seconds
import kotlin.time.DurationUnit

fun main() {
    val durations = listOf(2.5.seconds, 1.seconds / 3, 1500.milliseconds, 125.milliseconds, 375.milliseconds,
        625.microseconds, 1.nanoseconds, (-1).nanoseconds, Duration.ZERO, 90.minutes, 36.hours + 15.seconds,
        (-2.5).seconds, 123456789.nanoseconds, 0.5.seconds, 3.5.seconds, 2.5.milliseconds, 100000.days,
        (Long.MAX_VALUE / 2 - 1).milliseconds, Duration.INFINITE, (-7).days - 1.nanoseconds, 999999999.nanoseconds, 1.seconds / 7)
    for (d in durations)
        for (unit in DurationUnit.entries)
            println("$d in $unit: " + (0..6).joinToString(" ") { d.toString(unit, it) })
    println("12 decimals: ${(1.seconds / 3).toString(DurationUnit.SECONDS, 12)} ${10.nanoseconds.toString(DurationUnit.DAYS, 12)}")
    println("more than 12: ${(1.seconds / 3).toString(DurationUnit.SECONDS, 20)} ${(2.seconds / 3).toString(DurationUnit.HOURS, 99)}")
    println("default: ${2.5.seconds.toString(DurationUnit.MILLISECONDS)} ${Duration.INFINITE.toString(DurationUnit.SECONDS, 2)} " +
        "${(-Duration.INFINITE).toString(DurationUnit.DAYS, 3)}")
    println("negative decimals: " + try { 1.seconds.toString(DurationUnit.SECONDS, -1) } catch (e: IllegalArgumentException) { e.message })
}
