// Copyright 2026 the kmicro authors (NOTICE).
// SPDX-License-Identifier: Apache-2.0
@file:OptIn(kotlinx.cinterop.ExperimentalForeignApi::class, kotlin.experimental.ExperimentalNativeApi::class)
import drv.*
import kotlinx.cinterop.*
import kotlin.native.CName

// Each function exercises one cinterop shape against drv.h; drv.c calls them by their @CName names and checks the
// results.

@CName("kt_global")
fun global(): Int {                                         // a C global, read and written
    drv_counter = drv_counter + 5
    return drv_counter
}

@CName("kt_struct_return")
fun structReturn(): Int = pt_make(3, 4).useContents { x * 10 + y }

@CName("kt_struct_arg")
fun structArg(): Int = pt_sum(cValue<pt_t> { x = 30; y = 12 })

// 2.0f as the first member: its bits are an address in RAM, so a result written through it would go unnoticed
@CName("kt_float_struct_return")
fun floatStructReturn(): Int = vec_scale(cValue<vec2_t> { x = 2.0f; y = 3.5f }, 2.0f).useContents {
    (x * 100 + y).toInt()                                   // 4.0, 7.0
}

@CName("kt_double_struct_return")
fun doubleStructReturn(): Int = cplx_conj(cValue<cplx_t> { re = 12.0; im = -25.0 }).useContents {
    (re * 100 + im).toInt()                                 // 12.0, 25.0
}

@CName("kt_float_struct_callback")
fun floatStructCallback(): Int =                            // C calls Kotlin, which returns the struct to C
    vec_apply(staticCFunction { v: CValue<vec2_t>, k: Float ->
        v.useContents { cValue<vec2_t> { x = this@useContents.x * k; y = this@useContents.y * k } }
    })                                                      // 3.0, -5.0

@CName("kt_float_struct_loop")
fun floatStructLoop(): Int = vec_count(6000)

@CName("kt_one_float_struct")
fun oneFloatStruct(): Int = one_half(cValue<one_t> { v = 42.0f }).useContents { v.toInt() }

fun twice(x: Int): Int = x * 2

@CName("kt_callback")
fun callback(): Int {                                       // C keeps a Kotlin function and calls it later
    drv_set_cb(staticCFunction { x: Int -> twice(x) })
    return drv_fire(21)
}

@CName("kt_sort_descending")
fun sortDescending(): Int = memScoped {                     // a Kotlin comparator called by qsort
    val v = allocArray<IntVar>(5)
    intArrayOf(3, 9, 1, 7, 5).forEachIndexed { i, x -> v[i] = x }
    drv_sort(v, 5, staticCFunction { a: COpaquePointer?, b: COpaquePointer? ->
        b!!.reinterpret<IntVar>().pointed.value - a!!.reinterpret<IntVar>().pointed.value
    })
    (0 until 5).fold(0) { acc, i -> acc * 10 + v[i] }
}

@CName("kt_varargs")
fun varargs(): Int = sum_va(3, 1, 2, 3)

@CName("kt_inline_loop")
fun inlineLoop(): Int = sum_to(4u).toInt()

@CName("kt_inline_asm")
fun inlineAsm(): Int = add_one_asm(41u).toInt()

@CName("kt_inline_string")
fun inlineString(): Int {
    val s = slot_name()!!.toKString()
    println("slot_name() = \"$s\"")
    return if (s == "slot #1") 1 else 0
}

@CName("kt_inline_restrict")
fun inlineRestrict(): Int = memScoped {
    val src = allocArray<IntVar>(4)
    val dst = allocArray<IntVar>(4)
    for (i in 0 until 4) src[i] = i * 3
    copy_sum(dst, src, 4)
}

// An exception thrown inside a staticCFunction does not reach a Kotlin try around the C call that ran it: as on stock
// Kotlin/Native, the program stops with the uncaught-exception report. (Catch it inside the callback instead.)
@CName("kt_callback_throws")
fun callbackThrows(): Int {
    drv_set_cb(staticCFunction { x: Int -> if (x > 0) throw IllegalStateException("from callback $x"); x })
    return try { drv_fire(1) } catch (e: IllegalStateException) { println("caught: ${e.message}"); -7 }
}
