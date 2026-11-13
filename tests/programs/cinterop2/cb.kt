@file:OptIn(kotlinx.cinterop.ExperimentalForeignApi::class)
import drv.*
import kotlinx.cinterop.*

// Each function exercises one cinterop shape against tests/programs/cinterop2/drv.h; drv.c checks the results.

fun global(): Int {                                         // a C global, read and written
    drv_counter = drv_counter + 5
    return drv_counter
}

fun structReturn(): Int = pt_make(3, 4).useContents { x * 10 + y }

fun structArg(): Int = pt_sum(cValue<pt_t> { x = 30; y = 12 })

fun twice(x: Int): Int = x * 2

fun callback(): Int {                                       // C keeps a Kotlin function and calls it later
    drv_set_cb(staticCFunction { x: Int -> twice(x) })
    return drv_fire(21)
}

fun sortDescending(): Int = memScoped {                     // a Kotlin comparator called by qsort
    val v = allocArray<IntVar>(5)
    intArrayOf(3, 9, 1, 7, 5).forEachIndexed { i, x -> v[i] = x }
    drv_sort(v, 5, staticCFunction { a: COpaquePointer?, b: COpaquePointer? ->
        b!!.reinterpret<IntVar>().pointed.value - a!!.reinterpret<IntVar>().pointed.value
    })
    (0 until 5).fold(0) { acc, i -> acc * 10 + v[i] }
}

fun varargs(): Int = sum_va(3, 1, 2, 3)
