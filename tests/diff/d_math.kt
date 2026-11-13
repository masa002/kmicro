// kotlin.math: Double and Float functions over a spread of inputs, special values and corner cases.
// difftest: ulp 2 -- kmicro's kotlin.math is newlib's libm (fdlibm), the host's is another libm: transcendental results may differ in the last bit (0.0 and -0.0 count as equal)
import kotlin.math.*

fun <T> opaque(v: T): T = listOf(v).first()

// sin, cos and tan only where the Windows reference is exact: its x87 instructions lose precision for large arguments
// and next to multiples of pi (there kmicro's results are the correct ones).
fun trig(x: Double) = if (abs(x) < 1000.0 && abs(sin(x)) > 1e-3) "${sin(x)} ${cos(x)} ${tan(x)}" else "-"

fun main() {
    val xs = doubleArrayOf(-7.5, -2.0, -0.7, -0.1, 0.0, 0.1, 0.3, 0.5, 0.7, 1.0, 1.3, 2.0, 2.5, 3.0, 10.0, 100.0, 1e5, 1e10,
                           0.123456789, 6.283185307179586)
    for (x in xs) println("$x: ${trig(x)} ${exp(x)} ${atan(x)} ${sinh(x)} ${cosh(x)} ${tanh(x)} ${cbrt(x)} ${expm1(x)}")
    // 1.7.pow(x) only below 50: for 1.7^100 the Windows reference is 9 units in the last place off
    for (x in xs) if (x > 0) println("$x: ${ln(x)} ${log10(x)} ${log2(x)} ${ln1p(x)} ${x.pow(0.37)} ${x.pow(2.5)} ${if (x < 50) 1.7.pow(x) else "-"} ${atan2(x, 0.3)} ${hypot(x, 1.1)}")
    for (x in xs) if (x >= -1 && x <= 1) println("$x: ${asin(x)} ${acos(x)} ${atanh(x * 0.9)} ${asinh(x)}")
    val fs = floatArrayOf(-7.5f, -0.7f, 0.1f, 0.3f, 0.7f, 1.3f, 2.5f, 10.0f, 1e5f, 0.123456789f)
    for (f in fs) println("$f: ${sin(f)} ${cos(f)} ${tan(f)} ${exp(f)} ${atan(f)} ${cbrt(f)} ${tanh(f)} ${f.pow(1.7f)} ${hypot(f, 3f)}")
    for (f in fs) if (f > 0) println("$f: ${ln(f)} ${log10(f)} ${log2(f)} ${sqrt(f)}")

    val ys = opaque(listOf(0.0, -0.0, 0.5, -0.75, 1.0, 2.0, 3.141592653589793, 10.0, 1e-10, 100.25, -7.5, 1e300, Double.NaN, Double.POSITIVE_INFINITY))
    for (x in ys) {
        println("x=$x trig=${trig(x)} asin=${asin(x)} acos=${acos(x)} atan=${atan(x)} sinh=${sinh(x)} cosh=${cosh(x)} tanh=${tanh(x)}")
        println("   asinh=${asinh(x)} acosh=${acosh(x)} atanh=${atanh(x)} sqrt=${sqrt(x)} cbrt=${cbrt(x)} exp=${exp(x)} expm1=${expm1(x)} ln=${ln(x)} ln1p=${ln1p(x)} log10=${log10(x)} log2=${log2(x)}")
        println("   log3=${log(x, 3.0)} pow=${x.pow(2.5)} powI=${x.pow(3)} withSign=${x.withSign(-1.0)} nextUp=${x.nextUp()} nextDown=${x.nextDown()} ulp=${x.ulp} IEEErem=${x.IEEErem(0.3)} hypot=${hypot(x, 4.0)} atan2=${atan2(x, -2.0)} sign=${sign(x)}")
    }
    val fl = opaque(listOf(0f, 0.5f, -0.75f, 2f, 3.1415927f, 10f, 1e-10f, 1e30f, Float.NaN))
    for (x in fl) {
        println("f=$x trig=${if (abs(x) < 1000f) "${sin(x)} ${cos(x)} ${tan(x)}" else "-"} asin=${asin(x)} atan=${atan(x)} sinh=${sinh(x)} tanh=${tanh(x)} asinh=${asinh(x)} sqrt=${sqrt(x)} cbrt=${cbrt(x)} exp=${exp(x)} ln=${ln(x)} log10=${log10(x)} log2=${log2(x)} pow=${x.pow(1.5f)} ulp=${x.ulp} nextUp=${x.nextUp()} hypot=${hypot(x, 3f)} round=${round(x)}")
    }
    println("pow corners: ${0.0.pow(0.0)} ${Double.NaN.pow(0.0)} ${1.0.pow(Double.NaN)} ${1.0.pow(Double.POSITIVE_INFINITY)} ${(-1.0).pow(Double.POSITIVE_INFINITY)} ${(-8.0).pow(1.0 / 3)} ${2.0.pow(-1074)} ${10.0.pow(308)} ${10.0.pow(309)} ${(-2.0).pow(3)} ${2f.pow(10)}")
    println("hypot corners: ${hypot(Double.NaN, Double.POSITIVE_INFINITY)} ${hypot(1e308, 1e308)} ${hypot(3.0, 4.0)} ${hypot(Float.NEGATIVE_INFINITY, Float.NaN)}")
    println("log corners: ${ln(0.0)} ${ln(-1.0)} ${log(8.0, 2.0)} ${log(8.0, 1.0)} ${log(8.0, -2.0)} ${log10(1000.0)} ${log2(1024.0)} ${ln(E)} ${PI} ${E}")
    println("ulp corners: ${Double.MAX_VALUE.ulp} ${Double.MIN_VALUE.ulp} ${Double.POSITIVE_INFINITY.ulp} ${0.0.ulp} ${1.0.nextTowards(2.0)} ${1.0.nextTowards(1.0)} ${Float.MAX_VALUE.nextUp()} ${(-0.0).nextUp()} ${0.0.nextDown()}")
    println("int math: ${abs(-5)} ${abs(Int.MIN_VALUE)} ${abs(-5L)} ${max(3, 7)} ${min(3L, -7L)} ${sign(-2.0)} ${10.0.absoluteValue} ${maxOf(1, 9, 4)} ${minOf(3.5, 2.5, 9.0)}")
    println("done")
}
