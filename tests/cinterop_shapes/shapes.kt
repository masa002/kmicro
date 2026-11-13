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
