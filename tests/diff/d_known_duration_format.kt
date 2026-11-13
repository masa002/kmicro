// Known not to work on kmicro yet: Duration.toString(unit) and toString(unit, decimals) call the native
// Kotlin_DurationValue_formatToExactDecimals, which kmicro does not have. (The default toString works: d_lang_11.kt.)
// Not run by default: python tools/difftest.py d_known_duration_format
import kotlin.time.Duration.Companion.microseconds
import kotlin.time.Duration.Companion.minutes
import kotlin.time.Duration.Companion.seconds
import kotlin.time.DurationUnit

fun main() {
    println("toString(unit): ${1.5.seconds.toString(DurationUnit.MILLISECONDS)} ${90.minutes.toString(DurationUnit.HOURS, 2)} ${1234.microseconds.toString(DurationUnit.SECONDS, 4)}")
    println("${2.5.seconds.toString(DurationUnit.MILLISECONDS, 2)} ${(1.seconds / 3).toString(DurationUnit.SECONDS, 3)}")
    println("done")
}
