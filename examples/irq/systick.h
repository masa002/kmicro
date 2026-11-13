/* The SysTick timer of the Cortex-M4, written the way CMSIS core_cm4.h describes it: a register struct, the base
 * address and an instance macro, and _Pos/_Msk bit macros. tools/gen_regs.py reads this layout; with a real device,
 * pass the vendor's core_cm4.h and device header instead. */
#ifndef SYSTICK_H
#define SYSTICK_H
#include <stdint.h>

#define __IM  volatile const
#define __IOM volatile

typedef struct {
    __IOM uint32_t CTRL;                        /* 0x00 control and status */
    __IOM uint32_t LOAD;                        /* 0x04 reload value */
    __IOM uint32_t VAL;                         /* 0x08 current value */
    __IM  uint32_t CALIB;                       /* 0x0C calibration */
} SysTick_Type;

#define SCS_BASE                    (0xE000E000UL)
#define SysTick_BASE                (SCS_BASE + 0x0010UL)
#define SysTick                     ((SysTick_Type *) SysTick_BASE)

#define SysTick_CTRL_COUNTFLAG_Pos  16U         /* 1: the counter reached 0 since CTRL was last read */
#define SysTick_CTRL_COUNTFLAG_Msk  (1UL << SysTick_CTRL_COUNTFLAG_Pos)
#define SysTick_CTRL_CLKSOURCE_Pos  2U          /* 1: count the processor clock */
#define SysTick_CTRL_CLKSOURCE_Msk  (1UL << SysTick_CTRL_CLKSOURCE_Pos)
#define SysTick_CTRL_TICKINT_Pos    1U          /* 1: the SysTick exception when the counter reaches 0 */
#define SysTick_CTRL_TICKINT_Msk    (1UL << SysTick_CTRL_TICKINT_Pos)
#define SysTick_CTRL_ENABLE_Pos     0U
#define SysTick_CTRL_ENABLE_Msk     (1UL << SysTick_CTRL_ENABLE_Pos)
#define SysTick_LOAD_RELOAD_Pos     0U
#define SysTick_LOAD_RELOAD_Msk     (0xFFFFFFUL << SysTick_LOAD_RELOAD_Pos)

typedef enum {
    SysTick_IRQn = -1                           /* exception 15 */
} IRQn_Type;

#endif
