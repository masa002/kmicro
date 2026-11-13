@file:OptIn(kotlinx.cinterop.ExperimentalForeignApi::class, kotlin.reflect.ExperimentalAssociatedObjects::class)

// Smaller stdlib natives: vectorOf, String pinning, associated objects, and a Regex without CANON_EQ (it links the
// Unicode decomposition natives, which only CANON_EQ calls).
// difftest: heap 32768 -- the Regex engine builds its tables on the heap: the default 16 KB runs out
// difftest: large -- the Regex engine is about 240 KB of flash

import kotlin.reflect.AssociatedObjectKey
import kotlin.reflect.KClass
import kotlin.reflect.findAssociatedObject
import kotlinx.cinterop.UShortVar
import kotlinx.cinterop.addressOf
import kotlinx.cinterop.get
import kotlinx.cinterop.reinterpret
import kotlinx.cinterop.usePinned
import kotlinx.cinterop.vectorOf

@AssociatedObjectKey
@Retention(AnnotationRetention.BINARY)
annotation class Codec(val kClass: KClass<out Any>)

object Utf8Codec { override fun toString() = "Utf8Codec" }

@Codec(Utf8Codec::class)
class Frame

fun main() {
    val f = vectorOf(1.5f, -2f, 3.25f, 4f)
    val i = vectorOf(7, -8, 9, Int.MIN_VALUE)
    println("vector: ${(0..3).map { f.getFloatAt(it) }} ${(0..3).map { i.getIntAt(it) }} ${f.getIntAt(1)} ${i.getFloatAt(0)}")
    "aé漢".usePinned { p ->
        println("pinned: ${(0..2).map { p.addressOf(it).reinterpret<UShortVar>()[0].toString(16) }}")
        println("pinned out of range: " + try { p.addressOf(3); "no" } catch (e: IndexOutOfBoundsException) { "yes" })
    }
    println("associated: ${Frame::class.findAssociatedObject<Codec>()} ${String::class.findAssociatedObject<Codec>()}")
    val r = Regex("(\\d+)-(\\d+)")
    println("regex: ${r.find("from 12-345 to")?.groupValues} ${"a1b22c333".split(Regex("\\d+"))} ${"3.5".toDouble() * 2}")
}
