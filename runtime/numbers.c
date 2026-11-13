/* Numeric helpers (Operator.cpp of the stock runtime). Zero inputs to the bit counts return the bit width (the
 * stock code calls the builtins directly, which are undefined for zero in C). */
#include <math.h>
#include "kmicro.h"

KM_NOTHROW int32_t Kotlin_Float_toInt(float a)
{
    if (isnan(a)) return 0;
    if (a >= (float)INT32_MAX) return INT32_MAX;
    if (a <= (float)INT32_MIN) return INT32_MIN;
    return (int32_t)a;
}
KM_NOTHROW int64_t Kotlin_Float_toLong(float a)
{
    if (isnan(a)) return 0;
    if (a >= (float)INT64_MAX) return INT64_MAX;
    if (a <= (float)INT64_MIN) return INT64_MIN;
    return (int64_t)a;
}
KM_NOTHROW int8_t Kotlin_Float_toByte(float a) { return (int8_t)Kotlin_Float_toInt(a); }
KM_NOTHROW int16_t Kotlin_Float_toShort(float a) { return (int16_t)Kotlin_Float_toInt(a); }
KM_NOTHROW bool Kotlin_Float_isNaN(float a) { return isnan(a); }
KM_NOTHROW bool Kotlin_Float_isInfinite(float a) { return isinf(a); }

KM_NOTHROW int32_t Kotlin_Double_toInt(double a)
{
    if (isnan(a)) return 0;
    if (a >= (double)INT32_MAX) return INT32_MAX;
    if (a <= (double)INT32_MIN) return INT32_MIN;
    return (int32_t)a;
}
KM_NOTHROW int64_t Kotlin_Double_toLong(double a)
{
    if (isnan(a)) return 0;
    if (a >= (double)INT64_MAX) return INT64_MAX;
    if (a <= (double)INT64_MIN) return INT64_MIN;
    return (int64_t)a;
}
KM_NOTHROW bool Kotlin_Double_isNaN(double a) { return isnan(a); }
KM_NOTHROW bool Kotlin_Double_isInfinite(double a) { return isinf(a); }

KM_NOTHROW int32_t Kotlin_Int_countOneBits(int32_t v) { return __builtin_popcount((uint32_t)v); }
KM_NOTHROW int32_t Kotlin_Long_countOneBits(int64_t v) { return __builtin_popcountll((uint64_t)v); }
KM_NOTHROW int32_t Kotlin_Int_countTrailingZeroBits(int32_t v) { return v ? __builtin_ctz((uint32_t)v) : 32; }
KM_NOTHROW int32_t Kotlin_Long_countTrailingZeroBits(int64_t v) { return v ? __builtin_ctzll((uint64_t)v) : 64; }
KM_NOTHROW int32_t Kotlin_Int_countLeadingZeroBits(int32_t v) { return v ? __builtin_clz((uint32_t)v) : 32; }
KM_NOTHROW int32_t Kotlin_Long_countLeadingZeroBits(int64_t v) { return v ? __builtin_clzll((uint64_t)v) : 64; }
