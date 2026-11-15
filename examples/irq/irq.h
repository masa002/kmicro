/* Copyright 2026 the kmicro authors (NOTICE).
 * SPDX-License-Identifier: Apache-2.0 */
#pragma once
#include <stdint.h>

void SysTick_Handler(void);         /* Kotlin: irq.sysTickHandler(), called by the vector table */
int32_t run_ticks(int32_t n);       /* Kotlin: irq.runTicks(n: Int): Int */
void kt_init_all(void);             /* made by kbuild --init-all kt_init_all: every global of package irq */
