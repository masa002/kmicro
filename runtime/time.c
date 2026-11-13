/* kotlin.time and kotlin.random natives (Time.cpp of the stock runtime) on hooks the board provides (kmicro.h):
 *
 *   int64_t kmicro_time_ns(void)       monotonic nanoseconds from any origin: measureTime, TimeSource.Monotonic
 *   int64_t kmicro_wall_time_ns(void)  nanoseconds since 1970-01-01 UTC: Clock.System
 *   uint64_t kmicro_random_seed(void)  the seed of Random.Default
 *
 * A board without a clock leaves the first two out. The program then stops with a panic that names the missing hook
 * when it first asks for the time, instead of measuring with a made-up clock. Random needs no clock: constructing any
 * Random creates Random.Default, which seeds itself from the monotonic clock, and toolchain/retarget.py points that
 * read at kmicro_random_seed. Its default is a constant: Random(seed) gives the same numbers as on every Kotlin
 * platform, and Random.Default repeats its sequence after every reset unless the board returns something that varies
 * (a hardware RNG, ADC noise, a free-running timer). */
#include "kmicro.h"

__attribute__((weak)) int64_t kmicro_time_ns(void)
{
    kmicro_panic("measureTime and TimeSource.Monotonic need the board clock: int64_t kmicro_time_ns(void)");
}

__attribute__((weak)) int64_t kmicro_wall_time_ns(void)
{
    kmicro_panic("Clock.System needs the board's wall clock: int64_t kmicro_wall_time_ns(void)");
}

__attribute__((weak)) uint64_t kmicro_random_seed(void) { return 0; }

KM_NOTHROW int64_t Kotlin_system_getSteadyTimeNanos(void) { return kmicro_time_ns(); }
KM_NOTHROW int64_t Kotlin_system_getSteadyTimeMicros(void) { return kmicro_time_ns() / 1000; }
KM_NOTHROW int64_t Kotlin_system_getSteadyTimeMillis(void) { return kmicro_time_ns() / 1000000; }
KM_NOTHROW int64_t Kotlin_system_getSystemTimeNanos(void) { return kmicro_wall_time_ns(); }
