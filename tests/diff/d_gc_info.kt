// Copyright 2026 the kmicro authors (NOTICE).
// SPDX-License-Identifier: Apache-2.0
// GC.lastGCInfo: what it says about a collection. The numbers differ between the runtimes (times, counts, sizes of
// objects), so the program prints facts about them, and only facts that also hold when reading the info itself
// starts a collection (as it does under GC stress): what the last collection swept is not among them. kmicro
// measures collections from the first read of GC.lastGCInfo on, which is why main reads it once before anything else.
@file:OptIn(kotlin.native.runtime.NativeRuntimeApi::class, ExperimentalStdlibApi::class)

import kotlin.native.runtime.GC
import kotlin.native.runtime.GCInfo

class Box(val value: Int)

val keep = ArrayList<Box>()

fun churn(): Int {
    var sum = 0
    repeat(2000) { sum += "junk $it".length }
    return sum
}

// its own function, so that no frame slot of main keeps a GCInfo, with its maps, alive
fun collectAndRead(): GCInfo {
    GC.collect()
    return GC.lastGCInfo!!
}

fun heapBefore(i: GCInfo): Long = i.memoryUsageBefore["heap"]!!.totalObjectsSizeBytes

fun heapAfter(i: GCInfo): Long = i.memoryUsageAfter["heap"]!!.totalObjectsSizeBytes

fun kept(i: GCInfo): Long = i.sweepStatistics["heap"]!!.keptCount

fun ordered(i: GCInfo): Boolean = i.startTimeNs <= i.firstPauseRequestTimeNs &&
    i.firstPauseRequestTimeNs <= i.firstPauseStartTimeNs && i.firstPauseStartTimeNs <= i.firstPauseEndTimeNs &&
    i.firstPauseEndTimeNs <= i.endTimeNs

fun main() {
    GC.lastGCInfo
    println("churn ${churn()}")
    val a = collectAndRead()
    println("times in order: ${ordered(a)}")
    println("heap in use: before ${heapBefore(a) > 0}, after ${heapAfter(a) > 0}")
    println("roots: stack ${a.rootSet.stackReferences > 0}, global ${a.rootSet.globalReferences > 0}")

    repeat(200) { keep.add(Box(it)) }
    val b = collectAndRead()
    println("a later collection: ${b.epoch > a.epoch}, after the first: ${b.startTimeNs >= a.endTimeNs}")
    val marked = b.markedCount - a.markedCount >= 200
    val bytes = heapAfter(b) - heapAfter(a) >= 1600
    println("200 more objects: marked $marked, kept ${kept(b) - kept(a) >= 200}, bytes $bytes")

    keep.clear()
    val c = collectAndRead()
    println("dropped again: kept ${kept(b) - kept(c) >= 100}, bytes ${heapAfter(c) < heapAfter(b)}")
    println("read again: not an earlier collection ${GC.lastGCInfo!!.epoch >= c.epoch}")
}
