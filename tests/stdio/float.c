/* Copyright 2026 the kmicro authors (NOTICE).
 * SPDX-License-Identifier: Apache-2.0 */
/* Asks the linker for the floating-point conversions of newlib-nano's printf (%f %e %g): 10 to 13 KB of flash.
 * A board link can pass -u _printf_float instead. */
__asm__(".global _printf_float");
