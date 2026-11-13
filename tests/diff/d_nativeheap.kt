// nativeHeap / memScoped memory: blocks freed out of order are reused and merged, impossible sizes throw a catchable
// OutOfMemoryError (finally runs), and the memory is usable again afterwards. kmicro keeps this memory in a small
// arena (KM_INTEROP_BYTES, 1 KB by default), so a request that fits the host may not fit here: those checks print
// only that the program went on.
@file:OptIn(kotlinx.cinterop.ExperimentalForeignApi::class)

import kotlinx.cinterop.*

fun swap() {
    var buf = nativeHeap.allocArray<ByteVar>(48)
    var rounds = 0
    try {
        repeat(200) {
            val next = nativeHeap.allocArray<ByteVar>(48)
            next[0] = it.toByte()
            nativeHeap.free(buf)
            buf = next
            rounds++
        }
    } finally {
        println("swap: $rounds rounds, last ${buf[0]}")
        nativeHeap.free(buf)
    }
}

// Eight blocks nearly fill a 1 KB arena; three freed neighbours (out of order) must merge for the 300-byte block.
fun coalesce() {
    val blocks = Array(8) { nativeHeap.allocArray<ByteVar>(112) }
    nativeHeap.free(blocks[2])
    nativeHeap.free(blocks[1])
    nativeHeap.free(blocks[3])
    val big = try {
        nativeHeap.allocArray<ByteVar>(300)
    } catch (e: OutOfMemoryError) {
        null
    }
    println("merged hole: ${if (big != null) "allocated" else "OutOfMemoryError"}")
    try {
        nativeHeap.free(nativeHeap.allocArray<ByteVar>(600))   // more than is left: OutOfMemoryError on kmicro
    } catch (e: OutOfMemoryError) {
    } finally {
        println("600 more bytes: went on")
    }
    if (big != null) {
        big[299] = 7
        nativeHeap.free(big)
    }
    for (i in intArrayOf(7, 0, 5, 4, 6)) nativeHeap.free(blocks[i])
    val all = nativeHeap.allocArray<ByteVar>(900)
    all[899] = 1
    println("after freeing everything: ${all[899]}")
    nativeHeap.free(all)
}

fun tooBig(what: String, size: Long) {
    try {
        nativeHeap.allocArray<ByteVar>(size)
        println("$what: allocated")
    } catch (e: OutOfMemoryError) {
        println("$what: OutOfMemoryError")
    } finally {
        println("$what: finally ran")
    }
}

fun main() {
    swap()
    coalesce()
    tooBig("negative size", -8)   // (sizes above the address space crash the host runtime, so none here)
    try {
        memScoped {
            val a = allocArray<IntVar>(4)
            a[3] = 3
            allocArray<ByteVar>(4096)[4095] = 1                      // OutOfMemoryError on kmicro
        }
    } catch (e: OutOfMemoryError) {
    } finally {
        println("4 KB memScoped: went on")
    }
    val s = memScoped { "after: " + allocArray<IntVar>(8).let { it[7] = 42; it[7] } }
    println(s)
}
