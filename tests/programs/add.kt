@file:OptIn(kotlin.experimental.ExperimentalNativeApi::class)

import kotlin.native.CName

@CName("k_add")
fun add(a: Int, b: Int): Int = a + b
