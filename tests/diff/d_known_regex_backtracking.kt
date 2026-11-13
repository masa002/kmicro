// Known not to work on kmicro: a backtracking Regex over a long input. The engine recurses for each repetition of a
// group, and on these 691 characters it needs more than the 45 KB of stack that QEMU's STM32L475 leaves next to this
// program's 48 KB heap: the stack guard stops it with "kmicro fault: stack overflow" (exit 99).
// Not run by default: python tools/difftest.py d_known_regex_backtracking
// difftest: heap 49152 -- enough heap for the patterns, so the stack is what runs out
// difftest: large -- a program that uses Regex is about 365 KB of flash
fun main() {
    val big = (1..200).joinToString(",")
    println("big: ${Regex("\\d+").findAll(big).sumOf { it.value.toInt() }} ${Regex("(\\d+),(\\d+)").findAll(big).count()} ${Regex("^(\\d+,)*\\d+$").matches(big)}")
    println("done")
}
