// Unsigned types: arithmetic, division, comparison, conversion, parsing, boxing.
import kotlin.math.*

fun err(label: String, block: () -> Any?) {
    val r = runCatching(block)
    val e = r.exceptionOrNull()
    println("$label: " + if (e == null) "ok ${r.getOrNull()}" else "${e::class.simpleName}: ${e.message}")
}

fun <T> opaque(v: T): T = listOf(v).first()

fun main() {
    // unsigned
    val u1 = opaque(4000000000u); val u2 = opaque(7u); val um = opaque(UInt.MAX_VALUE)
    println("UInt: ${u1 + u2} ${u1 * 2u} ${u1 / u2} ${u1 % u2} ${um + 1u} ${0u - 1u} ${u1 > u2} ${u1.compareTo(u2)} ${u1.toInt()} ${u1.toLong()} ${u1.toDouble()} ${um.toFloat()} ${u1 shr 4} ${u1.inv()} ${u1 and 0xFFu} ${u1.floorDiv(u2)} ${u1.mod(u2)} ${u1.countOneBits()} ${u1.rotateLeft(4)} ${u1.takeHighestOneBit()} ${(u1..u1 + 3u).toList()}")
    val ul = opaque(18000000000000000000uL); val ul2 = opaque(3uL)
    println("ULong: ${ul + ul2} ${ul * 2uL} ${ul / ul2} ${ul % 7uL} ${ul / opaque(10000000000uL)} ${ul % opaque(9999999967uL)} ${ULong.MAX_VALUE / 10uL} ${ULong.MAX_VALUE % 10uL} ${ul > Long.MAX_VALUE.toULong()} ${ul.toLong()} ${ul.toDouble()} ${ULong.MAX_VALUE.toFloat()} ${ul.toString(16)} ${ul.toString(36)} ${ul.countLeadingZeroBits()}")
    val ub = opaque(200.toUByte()); val us = opaque(60000.toUShort())
    println("UByte/UShort: ${ub + ub} ${(ub + ub).toUByte()} ${ub / 3u} ${ub.toInt()} ${ub.toByte()} ${us * 2u} ${us.toShort()} ${us.toInt()} ${ub > 100u} ${us.countOneBits()} ${UByte.MAX_VALUE} ${UShort.MIN_VALUE} ${ub.toString(16)} ${(ub.toInt() shl 1).toUByte()}")
    println("unsigned parse: ${"4294967295".toUInt()} ${"18446744073709551615".toULong()} ${"ff".toUByte(16)} ${"ffff".toUShort(16)} ${"FFFFFFFFFFFFFFFF".toULong(16)} ${"18446744073709551616".toULongOrNull()} ${"+5".toUIntOrNull()} ${"".toUIntOrNull()}")
    println("unsigned eq/box: ${listOf(1u, 2u, 3u).sum()} ${setOf(5u, 5u, 6u)} ${mapOf(1uL to "a")[1uL]} ${(1u as Any) == 1u} ${listOf(3u, 1u, 2u).sorted()} ${listOf(UInt.MAX_VALUE, 0u).maxOrNull()} ${1u.hashCode()} ${ULong.MAX_VALUE.hashCode()} ${UByte.MAX_VALUE.hashCode()}")
    err("UInt / 0") { u1 / opaque(0u) }
    err("ULong % 0") { ul % opaque(0uL) }
    err("toUInt bad") { "4294967296".toUInt() }
    println("done")
}
