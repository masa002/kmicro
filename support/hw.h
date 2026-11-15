/* Copyright 2026 the kmicro authors (NOTICE).
 * SPDX-License-Identifier: Apache-2.0 */
/* hw.h - what Kotlin cannot say by itself, one instruction each after LTO.
 *
 * Kotlin has no volatile memory access (@Volatile applies to properties only) and no way to emit a CPU instruction
 * such as WFI. Kotlin code reaches the hardware only through these functions (cinterop with support/hw.def, package
 * c). hw.c is compiled by clang with -flto, so a call such as hw_rd32(RCC_CR_ADDR) becomes one LDR in the Kotlin
 * function that made it.
 *
 *   hw_*   volatile: every access really happens, in program order (peripheral registers, DMA-shared memory)
 *   mem_*  plain: the compiler may merge or drop them like ordinary loads/stores (RAM buffers shared with C)
 */
#ifndef KT_HW_H
#define KT_HW_H

#include <stdbool.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {                                         /* a C++ file may include this header */
#endif

uint32_t hw_rd32(uint32_t addr);
void     hw_wr32(uint32_t addr, uint32_t v);
uint16_t hw_rd16(uint32_t addr);
void     hw_wr16(uint32_t addr, uint16_t v);
uint8_t  hw_rd8(uint32_t addr);
void     hw_wr8(uint32_t addr, uint8_t v);

uint32_t mem_rd32(uint32_t addr);
void     mem_wr32(uint32_t addr, uint32_t v);
uint16_t mem_rd16(uint32_t addr);
void     mem_wr16(uint32_t addr, uint16_t v);
uint8_t  mem_rd8(uint32_t addr);
void     mem_wr8(uint32_t addr, uint8_t v);

void     hw_dsb(void);
void     hw_isb(void);
void     hw_dmb(void);
void     hw_wfi(void);
void     hw_nop(void);
uint32_t hw_irq_save(void);               /* returns PRIMASK, then disables interrupts (CPSID i); on a Cortex-A or
                                             Cortex-R core the CPSR, then masks IRQ and FIQ (CPSID if) */
void     hw_irq_restore(uint32_t primask); /* re-enables interrupts only if they were enabled before */
uint32_t hw_ipsr(void);                   /* 0 in thread mode, else the active exception number; Cortex-M only */
uint32_t hw_basepri(void);                /* BASEPRI: 0 = no masking by priority */
void     hw_basepri_set(uint32_t v);
void     hw_basepri_max(uint32_t v);      /* BASEPRI_MAX: only ever raises the mask */
bool     hw_cycles_enable(void);          /* starts the DWT cycle counter at 0; false: this core or chip has none */
uint32_t hw_cycles(void);                 /* DWT->CYCCNT: core clock cycles, counted once hw_cycles_enable() ran;
                                             0 for ever where hw_cycles_enable() returns false */

#ifdef __cplusplus
}
#endif

#endif /* KT_HW_H */
