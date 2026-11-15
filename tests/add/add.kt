// Copyright 2026 the kmicro authors (NOTICE).
// SPDX-License-Identifier: Apache-2.0
@file:OptIn(kotlin.experimental.ExperimentalNativeApi::class)

import kotlin.native.CName

// The smallest test: main.c calls this function by its @CName name.
@CName("k_add")
fun add(a: Int, b: Int): Int = a + b
