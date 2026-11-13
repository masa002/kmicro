// String API: split, replace, substring, pad, trim, number parsing to Int/Long, StringBuilder, comparison.
// (String.toDouble: d_known_to_double.kt; Regex: d_regex.kt)
// difftest: heap 32768 -- the default 16 KB runs out: the free memory ends up in small pieces
// difftest: large -- most of the String and StringBuilder API in one program: about 305 KB of flash
fun err(label: String, block: () -> Any?) {
    val r = runCatching(block)
    val e = r.exceptionOrNull()
    println("$label: " + if (e == null) "ok ${r.getOrNull()}" else "${e::class.simpleName}: ${e.message}")
}

class Thing(val id: Int) { override fun toString() = "Thing#$id" }

fun main() {
    val s = "a,b;;c,d,,e"
    println("split str: ${s.split(",")} chars: ${s.split(',', ';')} multi: ${s.split(",", ";;")} limit: ${s.split(",", limit = 3)}")
    println("split empty: ${"".split(",")} ${",".split(",")} ignoreCase: ${"aXbxc".split("x", ignoreCase = true)} splitToSequence: ${"1 2  3".splitToSequence(" ").toList()}")
    println("replace: ${"banana".replace("an", "AN")} ${"banana".replace('a', 'o')} ${"BaNaNa".replace("na", "-", ignoreCase = true)} first: ${"banana".replaceFirst("an", "_")} ${"banana".replaceFirst('a', 'A')} range: ${"banana".replaceRange(1, 3, "[x]")} ${"banana".removeRange(0, 2)}")
    println("replace empty: ${"abc".replace("", "-")} removePrefix=${"prefix-body".removePrefix("prefix-")} removeSuffix=${"x.kt".removeSuffix(".kt")} removeSurrounding=${"(x)".removeSurrounding("(", ")")}")
    val path = "dir/sub/file.tar.gz"
    println("substring: ${path.substringBefore('/')} ${path.substringAfter("/")} ${path.substringBeforeLast('.')} ${path.substringAfterLast('/')} ${path.substringAfter('#', "none")} ${path.substring(4)} ${path.substring(4, 7)}")
    println("indexOf: ${path.indexOf("sub")} ${path.indexOf('/', 4)} ${path.lastIndexOf('/')} ${path.lastIndexOf("a")} ${path.indexOf("zz")} ${path.indexOf("")} ${path.lastIndexOf("")} ${path.indexOfFirst { it == '.' }} ${path.indexOfLast { it.isLetter() }} ${path.indexOfAny(charArrayOf('x', '.'))} ${"aAa".indexOf("A", ignoreCase = true)} ${"aAa".lastIndexOf('A', 1)}")
    println("starts/ends: ${path.startsWith("dir")} ${path.startsWith("DIR", ignoreCase = true)} ${path.endsWith(".GZ", true)} ${path.endsWith("gz")} ${path.startsWith("sub", 4)} contains=${"sub" in path} ${path.contains("SUB", ignoreCase = true)}")
    println("pad: [${"7".padStart(3, '0')}] [${"ab".padEnd(5)}] [${"long".padStart(2)}] repeat=${"ab".repeat(3)} ${"x".repeat(0)} reversed=${"héllo😀".reversed().length}")
    println("trim: [${"  x y \t\n".trim()}] [${"  x ".trimStart()}] [${"  x ".trimEnd()}] [${"--x--".trim('-')}] [${"12ab34".trim { it.isDigit() }}] [${" nb ".trim()}] [${" em".trim()}]")
    println("trimIndent: [${"""
        |first
        |  second
    """.trimMargin()}] [${"""
            a
              b
        """.trimIndent()}]")
    println("lines: ${"one\ntwo\r\nthree\rfour\n".lines()} lineSequence=${"a\nb".lineSequence().count()}")
    println("replaceFirstChar: ${"kotlin".replaceFirstChar { it.uppercase() }} ${"Kotlin".replaceFirstChar { it.lowercase() }} ${"".replaceFirstChar { it.uppercase() }} capitalize-like: ${"émile".replaceFirstChar { it.titlecase() }}")
    println("case ascii: ${"Hello World 123".uppercase()} ${"Hello World 123".lowercase()} ${'a'.uppercaseChar()} ${'Z'.lowercaseChar()} ${"MiXeD".map { if (it.isUpperCase()) it.lowercaseChar() else it.uppercaseChar() }.joinToString("")}")
    // parsing
    println("toInt: ${"42".toInt()} ${"-0".toInt()} ${"+7".toInt()} ${"2147483647".toInt()} toIntOrNull: ${"2147483648".toIntOrNull()} ${"".toIntOrNull()} ${"-".toIntOrNull()} ${" 1".toIntOrNull()} ${"１２".toIntOrNull()} ${"٣".toIntOrNull()}")
    println("toLong: ${"-9223372036854775808".toLong()} ${"9223372036854775808".toLongOrNull()} toShort: ${"-32768".toShort()} ${"32768".toShortOrNull()} toByte: ${"127".toByte()} ${"-129".toByteOrNull()}")
    println("radix: ${"ff".toInt(16)} ${"-101".toInt(2)} ${"zz".toInt(36)} ${"7fffffffffffffff".toLong(16)} ${"g".toIntOrNull(16)} ${"FF".toUByte(16)} ${255.toString(2)} ${(-255).toString(16)} ${Long.MIN_VALUE.toString(36)} ${Int.MIN_VALUE.toString(7)}")
    println("unsigned parse: ${"4294967295".toUInt()} ${"4294967296".toUIntOrNull()} ${"-1".toUIntOrNull()} ${"18446744073709551615".toULong()} ${"65535".toUShort()} ${"256".toUByteOrNull()}")
    println("toBoolean: ${"true".toBoolean()} ${"TRUE".toBoolean()} ${"yes".toBoolean()} ${"false".toBooleanStrictOrNull()} ${"True".toBooleanStrictOrNull()}")
    err("toInt bad") { "12a".toInt() }
    err("toInt empty") { "".toInt() }
    err("toLong overflow") { "99999999999999999999".toLong() }
    err("toUInt neg") { "-5".toUInt() }
    err("radix bad") { "1".toInt(37) }
    err("toBooleanStrict") { "TRUE".toBooleanStrict() }
    // StringBuilder
    val sb = StringBuilder("start")
    sb.append(1).append(-2L).append('c').append(true).append(3.25).append(1.5f).append(null as String?).append(charArrayOf('x', 'y')).append(Thing(7)).append("str" as CharSequence).append(0.1 + 0.2).append(Long.MIN_VALUE).append(1e-7).append(Float.NaN)
    println("append: $sb len=${sb.length}")
    sb.clear(); sb.append("0123456789")
    sb.insert(0, "<").insert(sb.length, '>').insert(3, 42).insert(2, true).insert(1, 2.5).insert(1, null as Any?)
    println("insert: $sb")
    sb.deleteAt(0); sb.deleteRange(0, 4); sb[0] = '#'; sb.set(1, '$')
    println("delete/set: $sb indexOf=${sb.indexOf("5")} lastIndexOf=${sb.lastIndexOf("e")} substring=${sb.substring(2, 5)} get=${sb[3]}")
    sb.setLength(6); println("setLength 6: [$sb]"); sb.setLength(8); println("setLength 8: [${sb.toString().replace('\u0000', '0')}] len=${sb.length}")
    sb.reverse(); println("reverse: [${sb.toString().replace('\u0000', '0')}]")
    val sb2 = StringBuilder(); sb2.append("a😀b"); sb2.reverse(); println("reverse surrogate: ${sb2} ${sb2.length}")
    val cap = StringBuilder(4); cap.append("12345678901234567890"); println("capacity>=len: ${cap.capacity() >= cap.length} ensure: ${cap.apply { ensureCapacity(100) }.capacity() >= 100}")
    println("appendLine/Range: ${buildString { appendLine("l1"); append("abcdef", 1, 3); appendRange("xyz", 0, 2); repeat(3) { append(it) } }.replace("\n", "\\n")}")
    println("sb compare: ${StringBuilder("ab").toString() == "ab"} ${StringBuilder("ab").contentEquals("ab")}")
    err("sb insert oob") { StringBuilder("ab").insert(5, "x") }
    err("sb deleteAt oob") { StringBuilder("ab").deleteAt(2) }
    err("sb setLength neg") { StringBuilder("ab").setLength(-1) }
    // comparison
    println("compareTo: ${"a".compareTo("z")} ${"z".compareTo("a")} ${"abc".compareTo("ab")} ${"ab".compareTo("abcd")} ${"".compareTo("x")} ${"A".compareTo("a")} ${"é".compareTo("e")} ${"日本".compareTo("日")}")
    println("compareTo ignoreCase: ${"Apple".compareTo("apple", ignoreCase = true)} ${"apple".compareTo("BANANA", true)} ${"a".compareTo("B")} equalsIC=${"Straße".equals("STRASSE", true)} ${"ÄÖ".equals("äö", ignoreCase = true)} ${"Kotlin".equals("KOTLIN", true)} ${"ǅ".equals("ǆ", true)}")
    println("hashCode: ${"".hashCode()} ${"a".hashCode()} ${"Hello Kotlin".hashCode()} ${"日本語".hashCode()} ${"😀".hashCode()} ${"polygenelubricants".hashCode()} ${"a".repeat(100).hashCode()}")
    println("chars: ${"abc".toCharArray().contentToString()} ${charArrayOf('h', 'i').concatToString()} ${"hello".toCharArray(1, 3).concatToString()} ${"x😀".toList()} ${"ab".asIterable().joinToString("|")}")
    println("misc: ${"a-b-c".count { it == '-' }} ${"Hello".all { it.isLetter() }} ${"ab12".filter { it.isDigit() }} ${"abc".map { it.code }} ${"hello".toSet().size} ${"kotlin".chunked(4)} ${"kotlin".windowed(3)} ${"aab".groupingBy { it }.eachCount()} ${"abc".zip("xyz")} ${"a.b".split('.').joinToString("/")}")
    println("isBlank: ${"  ".isBlank()} ${"".isEmpty()} ${" a".isNotBlank()} ${(null as String?).isNullOrEmpty()} ${"x".ifEmpty { "e" }} ${"".ifBlank { "b" }} orEmpty=[${(null as String?).orEmpty()}] commonPrefix=${"kotlinx".commonPrefixWith("kotlin native")} commonSuffix=${"ending".commonSuffixWith("pending")}")
    println("templates: ${1}${'c'}${2.0}${null}${true}${listOf(1)}${Thing(3)} ${"\$"} ${"A\t|"} ${"""raw\n${1 + 1}"""}")
    println("string ops: ${"abc" + 1 + 2L + 'd' + 1.5} ${"abc".plus(null)} ${"x".first()} ${"xyz".last()} ${"xyz".getOrNull(5)} ${"xyz".elementAt(1)} ${"ABC".decapitalizeLike()}")
    err("String get oob") { "abc"[3] }
    err("substring bad") { "abc".substring(2, 1) }
    err("first empty") { "".first() }
    err("repeat neg") { "a".repeat(-1) }
    err("padStart neg") { "a".padStart(-1) }
    println("done")
}

fun String.decapitalizeLike() = replaceFirstChar { it.lowercaseChar() }
