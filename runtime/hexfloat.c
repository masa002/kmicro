/* Hexadecimal floating-point text ("0x1.8p1") for String.toDouble()/toFloat() and their OrNull forms: the stdlib's
 * HexStringParser (kotlin/native/internal/HexStringParser.kt, from Apache Harmony) step by step, without its regular
 * expressions. toolchain/retarget.py turns HexStringParser.Companion.parseDouble/parseFloat into calls to the two
 * functions at the end, so a program that parses numbers no longer links the Regex engine or compiles a pattern on
 * the heap at its first parse. Same grammar (HEX_PATTERN), same rounding, same NumberFormatException. */
#include "kmicro.h"

int32_t Kotlin_String_getStringLength(const ObjHeader *s);
uint16_t Kotlin_String_get(const ObjHeader *s, int32_t index);
__attribute__((noreturn)) void ThrowNumberFormatException(void);

#define MAX_SIGNIFICANT_LENGTH 15                   /* hex digits that go into the mantissa; the rest only rounds */

/* HEX_PATTERN, matched as a whole (ASCII classes only, as in the stdlib's Regex):
 *   [\x00-\x20]*([+-]?)0[xX](\p{XDigit}+\.?|\p{XDigit}*\.\p{XDigit}+)[pP]([+-]?\d+)[fFdD]?[\x00-\x20]*
 * The groups: the sign, the significand (its integer and fraction digits here) and the exponent with its sign. */
typedef struct {
    const ObjHeader *s;
    int negative;
    int32_t int_from, int_to, frac_from, frac_to, exp_from, exp_to;
} Segments;

static uint16_t at(const Segments *g, int32_t i) { return Kotlin_String_get(g->s, i); }

static int hex_digit(uint16_t c)
{
    if (c >= '0' && c <= '9')
        return c - '0';
    if (c >= 'a' && c <= 'f')
        return c - 'a' + 10;
    if (c >= 'A' && c <= 'F')
        return c - 'A' + 10;
    return -1;
}

static void segments(Segments *g)
{
    int32_t n = Kotlin_String_getStringLength(g->s), i = 0;
    while (i < n && at(g, i) <= 0x20)
        i++;
    g->negative = 0;
    if (i < n && (at(g, i) == '+' || at(g, i) == '-'))
        g->negative = at(g, i++) == '-';
    if (i + 1 >= n || at(g, i) != '0' || (at(g, i + 1) != 'x' && at(g, i + 1) != 'X'))
        ThrowNumberFormatException();
    i += 2;
    g->int_from = i;
    while (i < n && hex_digit(at(g, i)) >= 0)
        i++;
    g->int_to = g->frac_from = g->frac_to = i;
    if (i < n && at(g, i) == '.') {
        g->frac_from = ++i;
        while (i < n && hex_digit(at(g, i)) >= 0)
            i++;
        g->frac_to = i;
    }
    if (g->int_to == g->int_from && g->frac_to == g->frac_from)
        ThrowNumberFormatException();                           /* no digit */
    if (i >= n || (at(g, i) != 'p' && at(g, i) != 'P'))
        ThrowNumberFormatException();
    g->exp_from = ++i;
    if (i < n && (at(g, i) == '+' || at(g, i) == '-'))
        i++;
    int32_t digits = i;
    while (i < n && at(g, i) >= '0' && at(g, i) <= '9')
        i++;
    if (i == digits)
        ThrowNumberFormatException();
    g->exp_to = i;
    if (i < n && (at(g, i) == 'f' || at(g, i) == 'F' || at(g, i) == 'd' || at(g, i) == 'D'))
        i++;
    while (i < n && at(g, i) <= 0x20)
        i++;
    if (i != n)
        ThrowNumberFormatException();
}

/* The digit k of the significand's digits without the point (the integer part, then the fraction). */
static int sig_digit(const Segments *g, int32_t k)
{
    int32_t ni = g->int_to - g->int_from;
    return hex_digit(at(g, k < ni ? g->int_from + k : g->frac_from + (k - ni)));
}

typedef struct {
    int exponent_width, mantissa_width;
    int64_t exponent;
    uint64_t mantissa;
    int abandoned;                                  /* abandonedNumber holds a nonzero digit */
} Parser;

static int signum(int64_t x) { return x == 0 ? 0 : x > 0 ? 1 : -1; }
static int bit_length(uint64_t v) { return v ? 64 - __builtin_clzll(v) : 0; }

/* checkedAddExponent: an overflow saturates at +-Long.MAX_VALUE */
static void add_exponent(Parser *p, int64_t offset)
{
    int64_t result = (int64_t)((uint64_t)p->exponent + (uint64_t)offset);
    int sign = signum(p->exponent);
    if (sign * signum(offset) > 0 && sign * signum(result) < 0)
        p->exponent = sign * INT64_MAX;
    else
        p->exponent = result;
}

/* parseExponent: an exponent beyond Long (toLong throws) becomes +-Long.MAX_VALUE without the bias */
static void parse_exponent(Parser *p, const Segments *g)
{
    int32_t i = g->exp_from;
    int sign = at(g, i) == '-' ? -1 : 1;
    if (at(g, i) == '+' || at(g, i) == '-')
        i++;
    uint64_t v = 0;
    for (; i < g->exp_to; i++) {
        unsigned d = at(g, i) - '0';
        if (v > ((uint64_t)INT64_MAX - d) / 10u) {
            p->exponent = sign * INT64_MAX;
            return;
        }
        v = v * 10u + d;
    }
    p->exponent = sign * (int64_t)v;
    add_exponent(p, ((int64_t)1 << (p->exponent_width - 1)) - 1);   /* EXPONENT_BASE */
}

/* fitMantissaInDesiredWidth, with discardTrailingBits */
static void fit_mantissa(Parser *p, int desired_width)
{
    int length = bit_length(p->mantissa);
    if (length > desired_width) {
        int n = length - desired_width;
        if (p->mantissa & ((1ull << n) - 1u))
            p->abandoned = 1;
        p->mantissa >>= n;
    } else {
        p->mantissa <<= desired_width - length;
    }
}

/* round: to nearest, ties to even; a carry out of the top bit moves the exponent up */
static void round_mantissa(Parser *p)
{
    int last_discarded = (int)(p->mantissa & 1u);
    p->mantissa >>= 1;
    int tail = (int)(p->mantissa & 1u);
    if (last_discarded && (p->abandoned || tail)) {
        int old_length = bit_length(p->mantissa);
        p->mantissa += 1u;
        if (old_length >= p->mantissa_width && bit_length(p->mantissa) > old_length)
            add_exponent(p, 1);
    }
}

/* parseMantissa */
static void parse_mantissa(Parser *p, const Segments *g)
{
    int64_t max_exponent = ((int64_t)1 << p->exponent_width) - 1, min_exponent = -(p->mantissa_width + 1);
    int32_t ndigits = (g->int_to - g->int_from) + (g->frac_to - g->frac_from), first = 0;
    while (first < ndigits && sig_digit(g, first) == 0)
        first++;
    if (first == ndigits) {                                     /* the significand is 0 */
        p->exponent = 0;
        p->mantissa = 0;
        return;
    }
    int64_t offset;                                             /* getOffset */
    int32_t int_zeros = 0;
    while (g->int_from + int_zeros < g->int_to && at(g, g->int_from + int_zeros) == '0')
        int_zeros++;
    if (g->int_from + int_zeros < g->int_to) {
        int32_t length = g->int_to - g->int_from - int_zeros;
        offset = (int64_t)(length - 1) * 4 + bit_length((uint64_t)hex_digit(at(g, g->int_from + int_zeros))) - 1;
    } else {
        int32_t i = 0;
        while (at(g, g->frac_from + i) == '0')
            i++;
        offset = (int64_t)(-i - 1) * 4 + bit_length((uint64_t)hex_digit(at(g, g->frac_from + i))) - 1;
    }
    add_exponent(p, offset);
    if (p->exponent >= max_exponent) {                          /* setInfinite */
        p->exponent = max_exponent;
        p->mantissa = 0;
        return;
    }
    if (p->exponent <= min_exponent) {                          /* setZero */
        p->exponent = 0;
        p->mantissa = 0;
        return;
    }
    p->mantissa = 0;
    for (int32_t k = first; k < ndigits; k++) {
        int d = sig_digit(g, k);
        if (k - first < MAX_SIGNIFICANT_LENGTH)
            p->mantissa = p->mantissa * 16u + (unsigned)d;
        else if (d)
            p->abandoned = 1;
    }
    if (p->exponent >= 1) {                                     /* processNormalNumber */
        fit_mantissa(p, p->mantissa_width + 2);
    } else {                                                    /* processSubNormalNumber */
        int desired_width = p->mantissa_width + 1 + (int)p->exponent;
        p->exponent = 0;
        fit_mantissa(p, desired_width);
    }
    round_mantissa(p);
    p->mantissa &= ((uint64_t)1 << p->mantissa_width) - 1u;
}

/* parse: the IEEE bits, sign | exponent | mantissa */
static uint64_t parse(const ObjHeader *s, int exponent_width, int mantissa_width)
{
    Segments g = { .s = s };
    segments(&g);
    Parser p = { .exponent_width = exponent_width, .mantissa_width = mantissa_width };
    parse_exponent(&p, &g);
    parse_mantissa(&p, &g);
    return ((uint64_t)g.negative << (mantissa_width + exponent_width)) | ((uint64_t)p.exponent << mantissa_width)
           | p.mantissa;
}

double kmicro_hex_to_double(const ObjHeader *s)
{
    uint64_t bits = parse(s, 11, 52);
    double d;
    __builtin_memcpy(&d, &bits, sizeof d);
    return d;
}

float kmicro_hex_to_float(const ObjHeader *s)
{
    uint32_t bits = (uint32_t)parse(s, 8, 23);
    float f;
    __builtin_memcpy(&f, &bits, sizeof f);
    return f;
}
