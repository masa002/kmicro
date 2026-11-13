// Known not to work on kmicro yet with the default 16 KB heap (nor with 64 KB): Regex beyond a few small patterns. The
// engine keeps its tables and compiled patterns on the heap, and \p{L} copies the Unicode category table there
// as well (d_regex.kt's patterns plus \p{L} need about 56 KB). (A few small patterns with a 32 KB heap: d_regex.kt.)
// Not run by default: python tools/difftest.py d_known_regex_heap
fun err(label: String, block: () -> Any?) {
    val r = runCatching(block)
    val e = r.exceptionOrNull()
    println("$label: " + if (e == null) "ok ${r.getOrNull()}" else "${e::class.simpleName}: ${e.message}")
}

fun main() {
    println("\\p{L}: " + Regex("""\p{L}+""").findAll("héllo wörld マイコン").map { it.value }.toList())
    val date = Regex("""(\d{4})-(\d{2})-(\d{2})""")
    println("matches: ${date.matches("2026-11-13")} ${date.matches("x2026-11-13")} ${"2026-11-13" matches date} containsMatchIn=${date.containsMatchIn("on 2026-11-13!")} matchesAt=${date.matchesAt("ab2026-01-02", 2)}")
    val m = date.find("from 2026-11-13 to 2027-01-02")!!
    println("find: ${m.value} range=${m.range} groups=${m.groupValues} g1=${m.groups[1]?.value}@${m.groups[1]?.range} next=${m.next()?.value}")
    val (y, mo, d) = m.destructured; println("destructured: $y/$mo/$d")
    println("findAll: ${date.findAll("2020-01-01 x 2021-02-02 y 2022-03-03").map { it.groupValues[1] }.toList()} startIndex: ${date.find("2020-01-01 2021-02-02", 1)?.value}")
    val named = Regex("""(?<key>\w+)=(?<value>[^;]*)""")
    for (mr in named.findAll("a=1;bee=two;c=")) println("named: ${mr.groups["key"]?.value} -> [${mr.groups["value"]?.value}]")
    println("replace: ${"a1b22c333".replace(Regex("\\d+"), "#")} ${"a1b22c333".replace(Regex("\\d+")) { "<${it.value.length}>" }} ${"John Smith".replace(Regex("(\\w+) (\\w+)"), "$2, $1")} ${"x-y".replace(Regex("(?<a>x)"), "\${a}\${a}")} first=${"aaa".replaceFirst(Regex("a"), "b")}")
    println("split: ${Regex("\\s*,\\s*").split("a , b,c ,  d")} ${Regex(",").split("a,b,c", 2)} ${"a1b2c3".split(Regex("\\d"))} splitToSequence=${Regex("-").splitToSequence("p-q-r").toList()}")
    val ic = Regex("kotlin", RegexOption.IGNORE_CASE)
    println("IGNORE_CASE: ${ic.findAll("Kotlin KOTLIN kOtLiN java").count()} ${Regex("ÄÖ", RegexOption.IGNORE_CASE).matches("äö")} ${Regex("σ", RegexOption.IGNORE_CASE).containsMatchIn("Σ")}")
    val ml = Regex("^\\w+$", RegexOption.MULTILINE)
    println("MULTILINE: ${ml.findAll("one\ntwo three\nfour").map { it.value }.toList()} without: ${Regex("^\\w+$").findAll("one\ntwo").count()} DOT_MATCHES_ALL: ${Regex("a.b", RegexOption.DOT_MATCHES_ALL).matches("a\nb")} ${Regex("a.b").matches("a\nb")}")
    println("COMMENTS: ${Regex("a  b # comment", RegexOption.COMMENTS).matches("ab")} LITERAL: ${Regex("a.b", RegexOption.LITERAL).matches("a.b")} ${Regex("a.b", RegexOption.LITERAL).matches("axb")} options=${ic.options} pattern=${ic.pattern}")
    println("\\d \\w \\s: ${Regex("\\d+").findAll("a12b٣4").map { it.value }.toList()} ${Regex("\\w+").findAll("héllo wörld_1").map { it.value }.toList()} ${Regex("\\s+").split("a \t\nb c")}")
    println("\\b: ${Regex("\\bcat\\b").findAll("cat concat cat's bobcat").count()} \\B: ${Regex("\\Bcat").findAll("cat concat bobcat").count()}")
    println("lookahead: ${Regex("\\w+(?=!)").find("hey you!")?.value} neg: ${Regex("\\d+(?!px)").findAll("10px 20em 30").map { it.value }.toList()} lookbehind: ${Regex("(?<=\\$)\\d+").find("cost \$42")?.value} neg: ${Regex("(?<!-)\\b\\d+").findAll("-5 6 -7 8").map { it.value }.toList()}")
    println("backref: ${Regex("(\\w)\\1").findAll("aabbcd eef").map { it.value }.toList()} named backref: ${Regex("(?<q>['\"]).*?\\k<q>").find("say 'hi' \"there\"")?.value}")
    println("quantifiers: ${Regex("a{2,3}").findAll("aaaaaaa").map { it.value }.toList()} lazy: ${Regex("<.+?>").find("<a><b>")?.value} possessive: ${Regex("a*+a").containsMatchIn("aaa")} atomic: ${Regex("(?>a+)b").matches("aaab")}")
    println("alternation/classes: ${Regex("cat|dog").findAll("dogcatbird").map { it.value }.toList()} ${Regex("[a-c&&[^b]]+").findAll("abcabc").map { it.value }.toList()} ${Regex("[^\\x00-\\x7F]+").find("abc€uro")?.value} ${Regex("\\u00e9").matches("é")} ${Regex("(?i)abc").matches("ABC")} ${Regex("(?s).+").matches("a\nb")}")
    println("escape: ${Regex.escape("a.b*c")} ${Regex(Regex.escape("1+1=2?")).matches("1+1=2?")} fromLiteral: ${Regex.fromLiteral("[x]").matches("[x]")} escapeReplacement: ${Regex.escapeReplacement("\$1\\")} ${"ab".replace(Regex("a"), Regex.escapeReplacement("\$0"))}")
    println("emoji: ${Regex(".").findAll("a😀b").map { it.value }.toList()} ${Regex("😀+").find("x😀😀y")?.range} ${Regex("[😀-😂]").matches("😁")}")
    println("toString: ${Regex("a+b")}")
    val big = (1..200).joinToString(",")
    println("big: ${Regex("\\d+").findAll(big).sumOf { it.value.toInt() }} ${Regex("(\\d+),(\\d+)").findAll(big).count()} ${Regex("^(\\d+,)*\\d+$").matches(big)}")
    err("bad pattern") { Regex("(unclosed") }
    err("bad pattern 2") { Regex("a{2,1}") }
    err("bad group ref") { "abc".replace(Regex("a"), "$2") }
    err("bad named group") { Regex("(?<x>a)").find("a")!!.groups["y"] }
    err("destructured too few") { Regex("(a)").find("a")!!.destructured.component2() }
    println("CANON_EQ next")
    err("CANON_EQ") { Regex("é", RegexOption.CANON_EQ).matches("é") }
    println("done")
}
