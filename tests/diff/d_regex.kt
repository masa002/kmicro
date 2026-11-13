// Regex: find, findAll with groups, replace with group references, split, IGNORE_CASE, destructured, matchEntire,
// \w \d \s. More patterns, or \p{L}, need more heap (d_known_regex_heap.kt).
// difftest: heap 32768 -- the Regex engine builds its tables on the heap: the default 16 KB runs out
// difftest: large -- a program that uses Regex is about 365 KB of flash
fun main() {
    val r = Regex("""(\w+)@(\w+)\.com""")
    println(r.find("mail: alice@example.com, bob@test.com")?.groupValues)
    println(r.findAll("alice@example.com bob@test.com").map { it.groupValues[1] }.toList())
    println("a1b22c333".replace(Regex("[0-9]+"), "#"))
    println("a, b;c".split(Regex("[,;] ?")))
    println(Regex("HELLO", RegexOption.IGNORE_CASE).matches("hello"))
    println(Regex("""(\w)=(\d+)""").findAll("x=12 y=345").joinToString { it.destructured.toList().toString() })
    println(Regex("""^\s*(\d{1,3})\.(\d{1,3})\s*$""").matchEntire(" 10.250 ")?.groupValues)
    println("Hello Kotlin".replace(Regex("""(\w+) (\w+)"""), "$2 $1"))
}
