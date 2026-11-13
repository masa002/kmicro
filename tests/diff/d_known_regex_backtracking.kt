// Known not to work on kmicro: a backtracking Regex over a long input. The engine recurses for each repetition of a
// group and needs about 64 KB of stack for these 692 characters; the stack runs into .bss and the program faults (exit
// 99) with no message.
// Not run by default: python tools/difftest.py d_known_regex_backtracking
// difftest: heap 49152 -- enough heap for the patterns, so the stack is what runs out
// difftest: large -- the Regex engine is about 240 KB of flash
fun main() {
    val big = (1..200).joinToString(",")
    println("big: ${Regex("\\d+").findAll(big).sumOf { it.value.toInt() }} ${Regex("(\\d+),(\\d+)").findAll(big).count()} ${Regex("^(\\d+,)*\\d+$").matches(big)}")
    println("done")
}
