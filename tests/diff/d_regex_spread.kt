// Copyright 2026 the kmicro authors (NOTICE).
// SPDX-License-Identifier: Apache-2.0
// Regex: many patterns, one after the other: classes, quantifiers, groups, lookaround, backreferences, flags,
// Unicode classes, surrogates, replace, split, and the errors. Each pattern is made inside its own call, so nothing
// of it is alive afterwards, and a collection follows it. The collection matters: the collector otherwise runs only
// when the heap is full, and the tables the engine keeps for the character classes it has met are then left all
// over the heap. The class with a supplementary character, [😀-😂], line 37, needs one block of 16,080 bytes.
// Without the collections the program stops there, on a 64 KB heap too: "wanted 16080 B, live after GC 20456 of
// 65536 B, largest free 3024 B in 54 free blocks" (docs/writing-kotlin.md, "Memory").
// difftest: heap 49152 -- the tables of the engine and the 16 KB block of one pattern
// difftest: large -- a program that uses Regex is about 366 KB of flash
@file:OptIn(kotlin.native.runtime.NativeRuntimeApi::class)

import kotlin.native.runtime.GC

var line = 0

fun show(what: String, block: () -> Any?) {
    line++
    val r = runCatching(block)
    val e = r.exceptionOrNull()
    println("$line $what: " + if (e == null) r.getOrNull() else "${e::class.simpleName}: ${e.message}")
    GC.collect()
}

fun found(m: MatchResult): String =
    m.value + "@" + m.range.first + (if (m.groupValues.size > 1) m.groupValues.drop(1).toString() else "")

fun all(p: String, s: String, vararg o: RegexOption) = show("/$p/ in '$s'") {
    Regex(p, o.toSet()).findAll(s).map { found(it) }.toList()
}

fun main() {
    all("""\p{L}+""", "héllo wörld マイコン")
    all("""(\d{4})-(\d{2})-(\d{2})""", "from 2026-11-13 to 2027-01-02")
    show("matchesAt") {
        Regex("""(\d{4})-(\d{2})""").let { "" + it.matchesAt("ab2026-01", 2) + it.matchAt("ab2026-01", 3) }
    }
    show("next") {
        Regex("""\d+""").find("a1b22c333")!!.let { m -> m.value + m.next()?.value + m.next()?.next()?.value }
    }
    show("named") {
        Regex("""(?<key>\w+)=(?<value>[^;]*)""").findAll("a=1;bee=two;c=").map { it.groups["key"]?.value }.toList()
    }
    show("replace") { "a1b22c333".replace(Regex("\\d+")) { "<${it.value.length}>" } }
    show("replace groups") {
        "John Smith".replace(Regex("(\\w+) (\\w+)"), "$2, $1") + "x-y".replace(Regex("(?<a>x)"), "\${a}\${a}")
    }
    show("split") {
        "" + Regex("\\s*,\\s*").split("a , b,c ,  d") + Regex(",").split("a,b,c", 2) + Regex("x*").split("axxb")
    }
    all("kotlin", "Kotlin KOTLIN kOtLiN java", RegexOption.IGNORE_CASE)
    show("case") {
        "" + Regex("ÄÖ", RegexOption.IGNORE_CASE).matches("äö") +
            Regex("σ", RegexOption.IGNORE_CASE).containsMatchIn("Σ")
    }
    all("^\\w+$", "one\ntwo three\nfour", RegexOption.MULTILINE)
    all("^\\w+$", "one\ntwo")
    show("dot") { "" + Regex("a.b", RegexOption.DOT_MATCHES_ALL).matches("a\nb") + Regex("a.b").matches("a\nb") }
    show("comments") {
        "" + Regex("a  b # comment", RegexOption.COMMENTS).matches("ab") +
            Regex("a.b", RegexOption.LITERAL).matches("axb")
    }
    all("\\d+", "a12b٣4")
    all("\\w+", "héllo wörld_1")
    all("\\bcat\\b", "cat concat cat's bobcat")
    all("\\Bcat", "cat concat bobcat")
    all("\\w+(?=!)", "hey you! now!")
    all("\\d+(?!px)", "10px 20em 30")
    all("(?<=\\$)\\d+", "cost \$42 and \$7")
    all("(?<!-)\\b\\d+", "-5 6 -7 8")
    all("(\\w)\\1", "aabbcd eef")
    all("(?<q>['\"]).*?\\k<q>", "say 'hi' \"there\"")
    all("a{2,3}", "aaaaaaa")
    all("<.+?>", "<a><b>")
    all("<.+>", "<a><b>")
    show("possessive, atomic") { "" + Regex("a*+a").containsMatchIn("aaa") + Regex("(?>a+)b").matches("aaab") }
    all("cat|dog|bird", "dogcatbirdcow")
    all("[a-c&&[^b]]+", "abcabc")
    all("[^\\x00-\\x7F]+", "abc€uro ünï")
    show("escapes") {
        "" + Regex("\\u00e9").matches("é") + Regex("\\Q.*\\E+").matches(".*.*") +
            Regex("\\p{Lu}\\p{Ll}+").matches("Élan")
    }
    show("classes") {
        "" + Regex("\\p{Alpha}+").matches("abc") + Regex("\\p{IsGreek}+").matches("αβγ") +
            Regex("\\p{Sc}").containsMatchIn("5 €")
    }
    show("Regex.escape") {
        Regex.escape("a.b*c") + Regex(Regex.escape("1+1=2?")).matches("1+1=2?") + Regex.escapeReplacement("\$1\\")
    }
    all(".", "a😀b")
    all("😀+", "x😀😀y")
    all("[😀-😂]", "😁😃")
    all("([01]?\\d|2[0-3]):([0-5]\\d)(?::([0-5]\\d))?", "at 7:05, 23:59:59 and 24:00")
    all("\\$\\{(\\w+)(?::-([^}]*))?\\}", "path=\${HOME}/\${DIR:-tmp}/\${X:-}")
    all("(a+)+b", "aaaaaaaaaaaab")
    all("(a|b)*?c", "abababc")
    all("(?:(\\d+)|(\\w+))\\s", "12 ab 3c ")
    all("^$", "")
    all("", "ab")
    all("a*", "baaa")
    all("(?m)^.*$", "x\r\ny\n")
    all("(?x) ( \\d+ ) \\s* ( [a-z]+ ) # number and unit", "12 kg, 7m")
    all("(?i:AB)c", "abc ABc abC")
    all("(?<year>\\d{4})(?<sep>[-/])(?<month>\\d\\d)\\k<sep>(?<day>\\d\\d)", "2026-11-16 2026/11/16 2026-11/16")
    all("\\d{3,}?", "1234567")
    all("(\\d)(?=(\\d{3})+$)", "1234567")
    show("thousands") { "1234567".replace(Regex("(\\d)(?=(\\d{3})+$)"), "$1,") }
    show("trim") { "  two  words  ".replace(Regex("^\\s+|\\s+$"), "").replace(Regex("\\s{2,}"), " ") }
    show("csv") { Regex(""",(?=(?:[^"]*"[^"]*")*[^"]*$)""").split("""a,"b,c",d,"e ""f"" g",""") }
    show("hex") { Regex("#(?:[0-9a-fA-F]{3}){1,2}\\b").findAll("#fff #12345 #a1B2c3 #xyz").map { it.value }.toList() }
    show("lines") { Regex("\\R").split("a\nb\r\nc\rd") }
    show("groups") { Regex("(a)?(b)?(c)").find("c")!!.let { m -> "" + m.groups.size + m.groups[1] + m.groupValues } }
    show("bad pattern") { Regex("(unclosed") }
    show("bad pattern 2") { Regex("a{2,1}") }
    show("bad pattern 3") { Regex("[a-") }
    show("bad pattern 4") { Regex("*a") }
    show("bad pattern 5") { Regex("\\k<nope>") }
    show("bad pattern 6") { Regex("(?<n>a)(?<n>b)") }
    show("bad group ref") { "abc".replace(Regex("a"), "$2") }
    show("bad named ref") { "abc".replace(Regex("a"), "\${nope}") }
    show("bad named group") { Regex("(?<x>a)").find("a")!!.groups["y"] }
    show("bad start") { Regex("a").find("aaa", 4) }
    println("done")
}
