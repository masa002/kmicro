/* kotlin.math natives (KotlinMath.cpp of the stock runtime) on newlib's libm. Same corner cases as the stock code;
 * asinh/acosh call libm directly (the stock custom versions only compensate for some host libms). */
#include <math.h>
#include <stdbool.h>
#include <stdint.h>

double Kotlin_math_sin(double x) { return sin(x); }
double Kotlin_math_cos(double x) { return cos(x); }
double Kotlin_math_tan(double x) { return tan(x); }
double Kotlin_math_asin(double x) { return asin(x); }
double Kotlin_math_acos(double x) { return acos(x); }
double Kotlin_math_atan(double x) { return atan(x); }
double Kotlin_math_atan2(double y, double x) { return atan2(y, x); }
double Kotlin_math_sinh(double x) { return sinh(x); }
double Kotlin_math_cosh(double x) { return cosh(x); }
double Kotlin_math_tanh(double x) { return tanh(x); }
double Kotlin_math_asinh(double x) { return asinh(x); }
double Kotlin_math_acosh(double x) { return acosh(x); }
double Kotlin_math_atanh(double x) { return atanh(x); }
double Kotlin_math_hypot(double x, double y)
{
    if (isinf(x) || isinf(y)) return INFINITY;
    if (isnan(x) || isnan(y)) return NAN;
    return hypot(x, y);
}
double Kotlin_math_sqrt(double x) { return sqrt(x); }
double Kotlin_math_exp(double x) { return exp(x); }
double Kotlin_math_expm1(double x) { return expm1(x); }
double Kotlin_math_ln(double x) { return log(x); }
double Kotlin_math_log10(double x) { return log10(x); }
double Kotlin_math_log2(double x) { return log2(x); }
double Kotlin_math_ln1p(double x) { return log1p(x); }
double Kotlin_math_ceil(double x) { return ceil(x); }
double Kotlin_math_floor(double x) { return floor(x); }
double Kotlin_math_round(double x) { return rint(x); }
double Kotlin_math_abs(double x) { return fabs(x); }
double Kotlin_math_cbrt(double x) { return cbrt(x); }
double Kotlin_math_Double_pow(double thiz, double x)
{
    if (x == 0.0 || x == -0.0) return 1.0;                       /* Kotlin corner cases */
    if (isinf(x) && (thiz == 1.0 || thiz == -1.0)) return NAN;
    return pow(thiz, x);
}
double Kotlin_math_Double_IEEErem(double thiz, double divisor) { return remainder(thiz, divisor); }
double Kotlin_math_Double_withSign(double thiz, double sign) { return copysign(thiz, sign); }
double Kotlin_math_Double_nextUp(double thiz) { return nextafter(thiz, HUGE_VAL); }
double Kotlin_math_Double_nextDown(double thiz) { return nextafter(thiz, -HUGE_VAL); }
double Kotlin_math_Double_nextTowards(double thiz, double to) { return thiz == to ? to : nextafter(thiz, to); }
bool Kotlin_math_Double_signBit(double thiz) { return signbit(thiz) != 0; }

float Kotlin_math_sinf(float x) { return sinf(x); }
float Kotlin_math_cosf(float x) { return cosf(x); }
float Kotlin_math_tanf(float x) { return tanf(x); }
float Kotlin_math_asinf(float x) { return asinf(x); }
float Kotlin_math_acosf(float x) { return acosf(x); }
float Kotlin_math_atanf(float x) { return atanf(x); }
float Kotlin_math_atan2f(float y, float x) { return atan2f(y, x); }
float Kotlin_math_sinhf(float x) { return sinhf(x); }
float Kotlin_math_coshf(float x) { return coshf(x); }
float Kotlin_math_tanhf(float x) { return tanhf(x); }
float Kotlin_math_asinhf(float x) { return asinhf(x); }
float Kotlin_math_acoshf(float x) { return acoshf(x); }
float Kotlin_math_atanhf(float x) { return atanhf(x); }
float Kotlin_math_hypotf(float x, float y)
{
    if (isinf(x) || isinf(y)) return INFINITY;
    if (isnan(x) || isnan(y)) return NAN;
    return hypotf(x, y);
}
float Kotlin_math_sqrtf(float x) { return sqrtf(x); }
float Kotlin_math_expf(float x) { return expf(x); }
float Kotlin_math_expm1f(float x) { return expm1f(x); }
float Kotlin_math_lnf(float x) { return logf(x); }
float Kotlin_math_log10f(float x) { return log10f(x); }
float Kotlin_math_log2f(float x) { return log2f(x); }
float Kotlin_math_ln1pf(float x) { return log1pf(x); }
float Kotlin_math_ceilf(float x) { return ceilf(x); }
float Kotlin_math_floorf(float x) { return floorf(x); }
float Kotlin_math_roundf(float x) { return rintf(x); }
float Kotlin_math_absf(float x) { return fabsf(x); }
float Kotlin_math_cbrtf(float x) { return cbrtf(x); }
float Kotlin_math_Float_pow(float thiz, float x)
{
    if (x == 0.0f || x == -0.0f) return 1.0f;
    if (isinf(x) && (thiz == 1.0f || thiz == -1.0f)) return NAN;
    return powf(thiz, x);
}
float Kotlin_math_Float_IEEErem(float thiz, float divisor) { return remainderf(thiz, divisor); }
float Kotlin_math_Float_withSign(float thiz, float sign) { return copysignf(thiz, sign); }
float Kotlin_math_Float_nextUp(float thiz) { return nextafterf(thiz, HUGE_VALF); }
float Kotlin_math_Float_nextDown(float thiz) { return nextafterf(thiz, -HUGE_VALF); }
float Kotlin_math_Float_nextTowards(float thiz, float to) { return thiz == to ? to : nextafterf(thiz, to); }
bool Kotlin_math_Float_signBit(float thiz) { return signbit(thiz) != 0; }

int32_t Kotlin_math_absi(int32_t x) { return x < 0 ? (int32_t)(0u - (uint32_t)x) : x; }
int64_t Kotlin_math_absl(int64_t x) { return x < 0 ? (int64_t)(0u - (uint64_t)x) : x; }
