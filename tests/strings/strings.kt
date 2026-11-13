@file:OptIn(kotlin.experimental.ExperimentalNativeApi::class)
import kotlin.native.CName

@CName("k_str")
fun str(n: Int): Int {
    var fail = 0
    val s = "battery $n mV, ok=${n > 2400}"
    if (s != "battery 2500 mV, ok=true") fail = fail or 1
    if (s.length != 24) fail = fail or 2
    if (s.hashCode() != (2137746472)) fail = fail or 4
    val parts = s.split(", ")
    if (parts.size != 2 || parts[1] != "ok=true") fail = fail or 8
    val r = s.replace('a', 'A')
    if (r.substring(0, 7) != "bAttery") fail = fail or 16
    val sb = StringBuilder()
    for (i in 1..5) sb.append(i).append(',')
    if (sb.toString() != "1,2,3,4,5,") fail = fail or 32
    val jp = "é漢字"
    if (jp.length != 3 || jp[1] != '漢') fail = fail or 64
    if (n.toString(16) != "9c4") fail = fail or 128
    if (!("abc" < "abd")) fail = fail or 256
    if ("ok=true" !in s || s.indexOf("mV") != 13) fail = fail or 512
    println("kotlin says: $s / $sb / $jp")
    return fail
}
