@file:OptIn(kotlin.experimental.ExperimentalNativeApi::class, kotlin.native.runtime.NativeRuntimeApi::class,
    kotlin.uuid.ExperimentalUuidApi::class, kotlin.native.concurrent.ObsoleteWorkersApi::class,
    ExperimentalStdlibApi::class)

import kotlin.native.CName
import kotlin.native.Platform
import kotlin.native.concurrent.Worker
import kotlin.native.ref.WeakReference
import kotlin.native.runtime.GC
import kotlin.uuid.Uuid

// The standard library's runtime natives as kmicro answers them: platform values, console input through the board's
// kmicro_getc, exitProcess, Uuid.random through kmicro_random_bytes, and the APIs kmicro does not support, which stop
// with a message naming them. One function per case of main.c.

@CName("k_platform")
fun platform() {
    println("os ${Platform.osFamily} cpu ${Platform.cpuArchitecture} le ${Platform.isLittleEndian} " +
        "unaligned ${Platform.canAccessUnaligned} debug ${Platform.isDebugBinary} " +
        "cpus ${Platform.getAvailableProcessors()} name ${Platform.programName}")
    GC.schedule()
    println("lastGCInfo ${GC.lastGCInfo} finalizer processor ${GC.MainThreadFinalizerProcessor.available}")
    println("readlnOrNull ${readlnOrNull()} readLine ${readLine()}")
    println("readln " + try { readln() } catch (e: Exception) { "${e::class.simpleName}" })
    println("nul: [a\u0000b] end")
    println("still running")
    kotlin.system.exitProcess(3)
}

@CName("k_input")
fun input() {
    while (true) {
        val line = readlnOrNull() ?: break
        println("line [$line] ${line.length}")
    }
    println("eof ${readlnOrNull()} ${readLine()}")
    println("readln " + try { readln() } catch (e: Exception) { "${e::class.simpleName}" })
}

class Node(val next: Node?, val v: Int)

fun churn(): Int {
    var n: Node? = null
    for (i in 0 until 300) n = Node(if (i % 50 == 0) null else n, i)
    GC.collect()
    var s = 0
    var p = n
    while (p != null) { s += p.v; p = p.next }
    return s
}

// RegexOption.CANON_EQ throws a catchable IllegalArgumentException; the program goes on allocating and collecting.
@CName("k_canon_eq")
fun canonEq() {
    for (i in 0 until 3) {
        val e = runCatching { Regex("e\u0301", RegexOption.CANON_EQ).matches("\u00e9") }.exceptionOrNull()
        println("canon $i ${e?.let { "${it::class.simpleName}: ${it.message}" }} churn ${churn()}")
    }
    println("inline (?c): " + try { Regex("(?c)ex").find("ex")?.value } catch (e: IllegalArgumentException) { "IAE" })
    println("regex ${Regex("([0-9]+)-([0-9]+)").find("a 12-34 b")?.groupValues} after churn ${churn()}")
}

@CName("k_weak_reference")
fun weakReference() {
    println(WeakReference(Any()).get())
}

@CName("k_worker")
fun worker() {
    println(Worker.current)
}

@CName("k_gc_tuning")
fun gcTuning() {
    GC.autotune = false
}

@CName("k_uuid")
fun uuid() {
    println(Uuid.random())
}
