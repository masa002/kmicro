/* Kotlin strings (KString.h/.cpp, ToString.cpp, Console.cpp of the stock runtime).
 *
 * A String is a CharArray-shaped object: ArrayHeader, then int32 hashCode_, uint16 flags_, then the data. count_
 * counts 16-bit units including the 6 bytes of hashCode_/flags_. flags_: [15:12] encoding (0 UTF-16, 1 Latin-1),
 * [1] ignore the last byte (odd Latin-1 length), [0] the hash code is 0. Latin-1 strings are made only when the
 * compiler's latin1Strings binary option is on (Kotlin_latin1Strings), exactly as the stock runtime does; both
 * encodings are always read. Fixed-length encodings only, so a unit is a character.
 */
#include <string.h>
#include "kmicro.h"

typedef struct {
    ArrayHeader a;
    int32_t hashCode_;
    uint16_t flags_;
    uint8_t data_[];
} StringHeader;

enum { HASH_IS_ZERO = 1, IGNORE_LAST_BYTE = 2, ENC_SHIFT = 12, ENC_UTF16 = 0, ENC_LATIN1 = 1 };
#define EXTRA_BYTES 6u                               /* offsetof(data_) - sizeof(ArrayHeader) */

extern const int32_t Kotlin_latin1Strings;
ObjHeader *TheEmptyString(ObjHeader **result);
__attribute__((noreturn)) void ThrowCharacterCodingException(void);

static inline const StringHeader *SH(const ObjHeader *s) { return (const StringHeader *)s; }
static inline unsigned enc(const ObjHeader *s) { return SH(s)->flags_ >> ENC_SHIFT; }
static inline uint32_t size_bytes(const ObjHeader *s)
{
    return SH(s)->a.count_ * 2u - EXTRA_BYTES - ((SH(s)->flags_ & IGNORE_LAST_BYTE) ? 1u : 0u);
}
static inline uint32_t len(const ObjHeader *s) { return enc(s) == ENC_LATIN1 ? size_bytes(s) : size_bytes(s) / 2u; }
static inline uint16_t at(const ObjHeader *s, uint32_t i)
{
    return enc(s) == ENC_LATIN1 ? SH(s)->data_[i] : ((const uint16_t *)SH(s)->data_)[i];
}

/* allocateString: all strings are Char arrays of (bytes + 6 [+1]) / 2 units */
static ObjHeader *alloc_string(unsigned encoding, uint32_t units, ObjHeader **result)
{
    if (units == 0)
        return TheEmptyString(result);
    uint32_t bytes = encoding == ENC_LATIN1 ? units : units * 2u;
    uint16_t flags = (uint16_t)((encoding << ENC_SHIFT) | ((bytes & 1u) ? IGNORE_LAST_BYTE : 0u));
    ObjHeader *s = kmicro_alloc_array(theStringTypeInfo, (int32_t)((bytes + EXTRA_BYTES + 1u) / 2u), result);
    ((StringHeader *)s)->flags_ = flags;
    return s;
}
static inline uint8_t *wdata(ObjHeader *s) { return ((StringHeader *)s)->data_; }

static bool latin1_ok_chars(const uint16_t *c, uint32_t n)
{
    for (uint32_t i = 0; i < n; i++)
        if (c[i] > 0xFF)
            return false;
    return true;
}

/* A string with the characters of src[from, from+n) (any encoding), in the narrowest allowed encoding. */
static ObjHeader *copy_range(const ObjHeader *src, uint32_t from, uint32_t n, ObjHeader **result)
{
    bool l1 = enc(src) == ENC_LATIN1;
    if (!l1 && Kotlin_latin1Strings)
        l1 = latin1_ok_chars((const uint16_t *)SH(src)->data_ + from, n);
    ObjHeader *s = alloc_string(l1 ? ENC_LATIN1 : ENC_UTF16, n, result);
    if (n == 0)
        return s;
    if (l1 && enc(src) == ENC_LATIN1)
        memcpy(wdata(s), SH(src)->data_ + from, n);
    else if (l1)
        for (uint32_t i = 0; i < n; i++)
            wdata(s)[i] = (uint8_t)at(src, from + i);
    else if (enc(src) == ENC_UTF16)
        memcpy(wdata(s), (const uint16_t *)SH(src)->data_ + from, n * 2u);
    else
        for (uint32_t i = 0; i < n; i++)
            ((uint16_t *)wdata(s))[i] = at(src, from + i);
    return s;
}

/* ---- String.kt ---- */

KM_NOTHROW int32_t Kotlin_String_getStringLength(const ObjHeader *s) { return (int32_t)len(s); }

uint16_t Kotlin_String_get(const ObjHeader *s, int32_t index)
{
    if ((uint32_t)index >= len(s))
        ThrowArrayIndexOutOfBoundsException();
    return at(s, (uint32_t)index);
}

ObjHeader *Kotlin_String_plusImpl(const ObjHeader *a, const ObjHeader *b, ObjHeader **result)
{
    uint32_t la = len(a), lb = len(b);
    if (la == 0)
        return km_return(result, (ObjHeader *)b);
    if (lb == 0)
        return km_return(result, (ObjHeader *)a);
    if (la + lb > 0x3FFFFFFFu)
        ThrowOutOfMemoryError();
    bool l1 = enc(a) == ENC_LATIN1 && enc(b) == ENC_LATIN1;
    ObjHeader *s = alloc_string(l1 ? ENC_LATIN1 : ENC_UTF16, la + lb, result);   /* a, b: rooted by the caller */
    if (l1) {
        memcpy(wdata(s), SH(a)->data_, la);
        memcpy(wdata(s) + la, SH(b)->data_, lb);
    } else {
        uint16_t *o = (uint16_t *)wdata(s);
        for (uint32_t i = 0; i < la; i++)
            o[i] = at(a, i);
        for (uint32_t i = 0; i < lb; i++)
            o[la + i] = at(b, i);
    }
    return s;
}

ObjHeader *Kotlin_String_unsafeStringFromCharArray(const ObjHeader *chars, int32_t start, int32_t size, ObjHeader **result)
{
    const uint16_t *c = (const uint16_t *)km_array_data((ArrayHeader *)chars) + start;
    bool l1 = Kotlin_latin1Strings && latin1_ok_chars(c, (uint32_t)size);
    ObjHeader *s = alloc_string(l1 ? ENC_LATIN1 : ENC_UTF16, (uint32_t)size, result);
    c = (const uint16_t *)km_array_data((ArrayHeader *)chars) + start;            /* non-moving: still valid */
    if (l1)
        for (int32_t i = 0; i < size; i++)
            wdata(s)[i] = (uint8_t)c[i];
    else if (size > 0)
        memcpy(wdata(s), c, (size_t)size * 2u);
    return s;
}

static void overwrite_array(const ObjHeader *s, ObjHeader *dest, int32_t dest_off, int32_t start, int32_t size)
{
    uint16_t *o = (uint16_t *)km_array_data((ArrayHeader *)dest) + dest_off;
    for (int32_t i = 0; i < size; i++)
        o[i] = at(s, (uint32_t)(start + i));
}

ObjHeader *Kotlin_String_toCharArray(const ObjHeader *s, ObjHeader *dest, int32_t dest_off, int32_t start,
                                     int32_t size, ObjHeader **result)
{
    overwrite_array(s, dest, dest_off, start, size);
    return km_return(result, dest);
}

int32_t Kotlin_StringBuilder_insertString(ObjHeader *builder, int32_t dist, const ObjHeader *from, int32_t src,
                                          int32_t count)
{
    overwrite_array(from, builder, dist, src, count);
    return count;
}

int32_t Kotlin_StringBuilder_insertInt(ObjHeader *builder, int32_t position, int32_t value)
{
    char b[12], *p = b + sizeof b;
    uint32_t u = value < 0 ? 0u - (uint32_t)value : (uint32_t)value;
    do {
        *--p = (char)('0' + u % 10u);
        u /= 10u;
    } while (u);
    if (value < 0)
        *--p = '-';
    int32_t n = (int32_t)(b + sizeof b - p);
    uint16_t *o = (uint16_t *)km_array_data((ArrayHeader *)builder) + position;
    for (int32_t i = 0; i < n; i++)
        o[i] = (uint16_t)p[i];
    return n;
}

ObjHeader *Kotlin_String_subSequence(const ObjHeader *s, int32_t start, int32_t end, ObjHeader **result)
{
    if (start < 0 || (uint32_t)end > len(s) || start > end)
        ThrowArrayIndexOutOfBoundsException();
    return copy_range(s, (uint32_t)start, (uint32_t)(end - start), result);
}

ObjHeader *Kotlin_String_replace(const ObjHeader *s, uint16_t old_c, uint16_t new_c, ObjHeader **result)
{
    uint32_t n = len(s);
    if (enc(s) == ENC_LATIN1 && old_c > 0xFF)
        return km_return(result, (ObjHeader *)s);
    bool l1 = enc(s) == ENC_LATIN1 && new_c <= 0xFF;
    ObjHeader *r = alloc_string(l1 ? ENC_LATIN1 : ENC_UTF16, n, result);
    for (uint32_t i = 0; i < n; i++) {
        uint16_t c = at(s, i);
        if (c == old_c)
            c = new_c;
        if (l1)
            wdata(r)[i] = (uint8_t)c;
        else
            ((uint16_t *)wdata(r))[i] = c;
    }
    return r;
}

KM_NOTHROW int32_t Kotlin_String_compareTo(const ObjHeader *a, const ObjHeader *b)
{
    uint32_t la = len(a), lb = len(b), n = la < lb ? la : lb;
    for (uint32_t i = 0; i < n; i++) {
        uint16_t x = at(a, i), y = at(b, i);
        if (x != y)
            return x < y ? -1 : 1;
    }
    return la == lb ? 0 : (la < lb ? -1 : 1);
}

static bool cached_hash(const ObjHeader *s, int32_t *h)
{
    if (size_bytes(s) == 0) {
        *h = 0;
        return true;
    }
    *h = SH(s)->hashCode_;
    return *h != 0 || (SH(s)->flags_ & HASH_IS_ZERO);
}

/* polyHash: the JVM String.hashCode over the UTF-16 code units (a Latin-1 byte is its code unit). */
int32_t Kotlin_String_hashCode(ObjHeader *s)
{
    int32_t h;
    if (cached_hash(s, &h))
        return h;
    uint32_t r = 0, n = len(s);
    for (uint32_t i = 0; i < n; i++)
        r = 31u * r + at(s, i);
    if (km_tag(s) != KM_TAG_PERMANENT) {             /* permanent strings live in flash: do not cache */
        if (r != 0)
            ((StringHeader *)s)->hashCode_ = (int32_t)r;
        else
            ((StringHeader *)s)->flags_ |= HASH_IS_ZERO;
    }
    return (int32_t)r;
}

KM_NOTHROW bool Kotlin_String_equals(const ObjHeader *a, const ObjHeader *b)
{
    if (a == b)
        return true;
    if (b == NULL || km_type_info(b) != theStringTypeInfo)
        return false;
    int32_t ha, hb;
    if (cached_hash(a, &ha) && cached_hash(b, &hb) && ha != hb)
        return false;
    uint32_t n = len(a);
    if (n != len(b))
        return false;
    if (enc(a) == enc(b))
        return memcmp(SH(a)->data_, SH(b)->data_, size_bytes(a)) == 0;
    for (uint32_t i = 0; i < n; i++)
        if (at(a, i) != at(b, i))
            return false;
    return true;
}

KM_NOTHROW bool Kotlin_String_unsafeRangeEquals(const ObjHeader *a, int32_t ao, const ObjHeader *b, int32_t bo, int32_t n)
{
    for (int32_t i = 0; i < n; i++)
        if (at(a, (uint32_t)(ao + i)) != at(b, (uint32_t)(bo + i)))
            return false;
    return true;
}

KM_NOTHROW bool Kotlin_Char_isISOControl(uint16_t c) { return c <= 0x1F || (c >= 0x7F && c <= 0x9F); }
KM_NOTHROW bool Kotlin_Char_isHighSurrogate(uint16_t c) { return (c & 0xFC00) == 0xD800; }
KM_NOTHROW bool Kotlin_Char_isLowSurrogate(uint16_t c) { return (c & 0xFC00) == 0xDC00; }

KM_NOTHROW int32_t Kotlin_String_indexOfChar(const ObjHeader *s, uint16_t c, int32_t from)
{
    uint32_t n = len(s);
    for (uint32_t i = from < 0 ? 0u : (uint32_t)from; i < n; i++)
        if (at(s, i) == c)
            return (int32_t)i;
    return -1;
}

KM_NOTHROW int32_t Kotlin_String_lastIndexOfChar(const ObjHeader *s, uint16_t c, int32_t from)
{
    if (from < 0)
        return -1;
    uint32_t i = (uint32_t)from + 1u, n = len(s);
    if (i > n)
        i = n;
    while (i-- > 0)
        if (at(s, i) == c)
            return (int32_t)i;
    return -1;
}

KM_NOTHROW int32_t Kotlin_String_indexOfString(const ObjHeader *s, const ObjHeader *p, int32_t from)
{
    uint32_t i0 = from < 0 ? 0u : (uint32_t)from, n = len(s), m = len(p);
    if (i0 >= n)
        return m == 0 ? (int32_t)n : -1;
    if (m > n)
        return -1;
    if (m == 0)
        return (int32_t)i0;
    for (uint32_t i = i0; i + m <= n; i++) {
        uint32_t k = 0;
        while (k < m && at(s, i + k) == at(p, k))
            k++;
        if (k == m)
            return (int32_t)i;
    }
    return -1;
}

/* ---- UTF-8 (with U+FFFD replacement, or a CharacterCodingException in the checked variants) ---- */

static uint32_t utf8_of(const ObjHeader *s, uint32_t start, uint32_t n, uint8_t *out, bool checked)
{
    uint32_t o = 0;
    for (uint32_t i = 0; i < n; i++) {
        uint32_t c = at(s, start + i);
        if (c >= 0xD800 && c <= 0xDFFF) {
            uint32_t d = i + 1 < n ? at(s, start + i + 1) : 0;
            if (c <= 0xDBFF && d >= 0xDC00 && d <= 0xDFFF) {
                c = 0x10000u + ((c - 0xD800u) << 10) + (d - 0xDC00u);
                i++;
            } else if (checked) {
                ThrowCharacterCodingException();
            } else {
                c = 0xFFFD;
            }
        }
        if (c < 0x80) {
            if (out) out[o] = (uint8_t)c;
            o += 1;
        } else if (c < 0x800) {
            if (out) { out[o] = (uint8_t)(0xC0 | c >> 6); out[o + 1] = (uint8_t)(0x80 | (c & 0x3F)); }
            o += 2;
        } else if (c < 0x10000) {
            if (out) { out[o] = (uint8_t)(0xE0 | c >> 12); out[o + 1] = (uint8_t)(0x80 | ((c >> 6) & 0x3F));
                       out[o + 2] = (uint8_t)(0x80 | (c & 0x3F)); }
            o += 3;
        } else {
            if (out) { out[o] = (uint8_t)(0xF0 | c >> 18); out[o + 1] = (uint8_t)(0x80 | ((c >> 12) & 0x3F));
                       out[o + 2] = (uint8_t)(0x80 | ((c >> 6) & 0x3F)); out[o + 3] = (uint8_t)(0x80 | (c & 0x3F)); }
            o += 4;
        }
    }
    return o;
}

extern const TypeInfo *theByteArrayTypeInfo;
static ObjHeader *to_utf8(const ObjHeader *s, int32_t start, int32_t size, bool checked, ObjHeader **result)
{
    uint32_t n = utf8_of(s, (uint32_t)start, (uint32_t)size, NULL, checked);
    ObjHeader *a = kmicro_alloc_array(theByteArrayTypeInfo, (int32_t)n, result);
    utf8_of(s, (uint32_t)start, (uint32_t)size, km_array_data((ArrayHeader *)a), checked);
    return a;
}
ObjHeader *Kotlin_String_unsafeStringToUtf8(const ObjHeader *s, int32_t start, int32_t size, ObjHeader **result)
{
    return to_utf8(s, start, size, false, result);
}
ObjHeader *Kotlin_String_unsafeStringToUtf8OrThrow(const ObjHeader *s, int32_t start, int32_t size, ObjHeader **result)
{
    return to_utf8(s, start, size, true, result);
}

/* The code point at u[i], decoded as the stock runtime's utfcpp does it (with_replacement::next): sets *used to the
 * bytes consumed and returns UTF8_BAD for a malformed sequence, which becomes one U+FFFD. An invalid lead byte, or a
 * value that is overlong, an encoded surrogate or above U+10FFFF (checked once the second byte is read), consumes one
 * byte. A sequence cut short by a missing continuation byte consumes the lead and the continuation bytes it has. */
#define UTF8_BAD 0xFFFFFFFFu
static uint32_t utf8_next(const uint8_t *u, uint32_t i, uint32_t n, uint32_t *used)
{
    uint32_t c = u[i];
    uint32_t len = c < 0x80 ? 1 : (c >> 5) == 0x6 ? 2 : (c >> 4) == 0xE ? 3 : (c >> 3) == 0x1E ? 4 : 0;
    *used = 1;
    if (len == 1)
        return c;
    if (len == 0)                                    /* a stray continuation byte or 0xF8..0xFF */
        return UTF8_BAD;
    c &= 0x7Fu >> len;
    for (uint32_t k = 1; k < len; k++) {
        if (i + k >= n || (u[i + k] & 0xC0) != 0x80) {
            *used = k;                               /* cut short */
            return UTF8_BAD;
        }
        c = (c << 6) | (u[i + k] & 0x3F);
        if (k == 1) {
            uint32_t v = c << (6 * (len - 2));       /* the value with the bytes still to come as zeros */
            if (len == 2 ? v < 0x80 : len == 3 ? v < 0x800 || (v & 0xF800) == 0xD800 : v < 0x10000 || v > 0x10FFFF)
                return UTF8_BAD;                     /* *used is still 1 */
        }
    }
    *used = len;
    return c;
}

/* Decode UTF-8 into UTF-16 units; returns the unit count. out == NULL: count only. */
static uint32_t utf16_of(const uint8_t *u, uint32_t n, uint16_t *out, bool checked)
{
    uint32_t o = 0;
    for (uint32_t i = 0; i < n;) {
        uint32_t used, c = utf8_next(u, i, n, &used);
        i += used;
        if (c == UTF8_BAD) {
            if (checked)
                ThrowCharacterCodingException();
            c = 0xFFFD;
        }
        if (c >= 0x10000) {
            if (out) { out[o] = (uint16_t)(0xD800 + ((c - 0x10000) >> 10)); out[o + 1] = (uint16_t)(0xDC00 + ((c - 0x10000) & 0x3FF)); }
            o += 2;
        } else {
            if (out) out[o] = (uint16_t)c;
            o += 1;
        }
    }
    return o;
}

static ObjHeader *from_utf8(const uint8_t *u, uint32_t n, bool checked, ObjHeader **result)
{
    if (u == NULL)
        return km_return(result, NULL);
    bool ascii = true;
    for (uint32_t i = 0; i < n && ascii; i++)
        ascii = u[i] < 0x80;
    if (ascii && Kotlin_latin1Strings) {
        ObjHeader *s = alloc_string(ENC_LATIN1, n, result);
        if (n)
            memcpy(wdata(s), u, n);
        return s;
    }
    uint32_t units = utf16_of(u, n, NULL, checked);
    ObjHeader *s = alloc_string(ENC_UTF16, units, result);
    if (units)
        utf16_of(u, n, (uint16_t *)wdata(s), checked);
    return s;
}

ObjHeader *CreateStringFromUtf8(const char *utf8, uint32_t n, ObjHeader **result)
{
    return from_utf8((const uint8_t *)utf8, n, false, result);
}
ObjHeader *CreateStringFromCString(const char *c, ObjHeader **result)
{
    return from_utf8((const uint8_t *)c, c ? (uint32_t)strlen(c) : 0u, false, result);
}
ObjHeader *Kotlin_CString_toKStringFromUtf8Impl(const char *c, ObjHeader **result) { return CreateStringFromCString(c, result); }
ObjHeader *Kotlin_ByteArray_unsafeStringFromUtf8(const ObjHeader *a, int32_t start, int32_t size, ObjHeader **result)
{
    return from_utf8((const uint8_t *)km_array_data((ArrayHeader *)a) + start, (uint32_t)size, false, result);
}
ObjHeader *Kotlin_ByteArray_unsafeStringFromUtf8OrThrow(const ObjHeader *a, int32_t start, int32_t size, ObjHeader **result)
{
    return from_utf8((const uint8_t *)km_array_data((ArrayHeader *)a) + start, (uint32_t)size, true, result);
}

/* Units making up the character at i: 2 for a surrogate pair (one supplementary character), else 1. */
static inline uint32_t char_units(const ObjHeader *s, uint32_t i, uint32_t n)
{
    uint16_t c = at(s, i);
    return (c >= 0xD800 && c <= 0xDBFF && i + 1 < n && (at(s, i + 1) & 0xFC00) == 0xDC00) ? 2u : 1u;
}

/* Copies a Kotlin string into a C buffer as UTF-8, NUL-terminated, truncated to cap - 1 bytes (kernel helper). */
uint32_t kmicro_string_to_utf8(const ObjHeader *s, char *buf, uint32_t cap)
{
    uint8_t tmp[4];
    uint32_t o = 0, n = s ? len(s) : 0;
    for (uint32_t i = 0; i < n;) {
        uint32_t u = char_units(s, i, n);
        uint32_t k = utf8_of(s, i, u, tmp, false);
        if (o + k + 1 > cap)
            break;
        memcpy(buf + o, tmp, k);
        o += k;
        i += u;
    }
    if (cap)
        buf[o] = 0;
    return o;
}

/* ---- ToString.cpp ---- */

static ObjHeader *ascii_string(const char *p, uint32_t n, ObjHeader **result)
{
    return from_utf8((const uint8_t *)p, n, false, result);
}

static ObjHeader *long_to_string(int64_t v, int32_t radix, ObjHeader **result)
{
    char b[66], *p = b + sizeof b;
    uint64_t u = v < 0 ? 0u - (uint64_t)v : (uint64_t)v;
    if (radix < 2 || radix > 36)
        radix = 10;
    do {
        uint32_t d = (uint32_t)(u % (uint32_t)radix);
        *--p = (char)(d < 10 ? '0' + d : 'a' + d - 10);
        u /= (uint32_t)radix;
    } while (u);
    if (v < 0)
        *--p = '-';
    return ascii_string(p, (uint32_t)(b + sizeof b - p), result);
}

ObjHeader *Kotlin_Byte_toString(int8_t v, ObjHeader **result) { return long_to_string(v, 10, result); }
ObjHeader *Kotlin_Short_toString(int16_t v, ObjHeader **result) { return long_to_string(v, 10, result); }
ObjHeader *Kotlin_Int_toString(int32_t v, ObjHeader **result) { return long_to_string(v, 10, result); }
ObjHeader *Kotlin_Int_toStringRadix(int32_t v, int32_t radix, ObjHeader **result) { return long_to_string(v, radix, result); }
ObjHeader *Kotlin_Long_toString(int64_t v, ObjHeader **result) { return long_to_string(v, 10, result); }
ObjHeader *Kotlin_Long_toStringRadix(int64_t v, int32_t radix, ObjHeader **result) { return long_to_string(v, radix, result); }
ObjHeader *Kotlin_Char_toString(uint16_t c, ObjHeader **result)
{
    bool l1 = Kotlin_latin1Strings && c <= 0xFF;
    ObjHeader *s = alloc_string(l1 ? ENC_LATIN1 : ENC_UTF16, 1, result);
    if (l1)
        wdata(s)[0] = (uint8_t)c;
    else
        ((uint16_t *)wdata(s))[0] = c;
    return s;
}

/* ---- Console.cpp: println goes to the platform's text output ---- */

/* UTF-8 text with a length, so a U+0000 character does not end it. A board whose output can take any byte (a UART,
 * semihosting SYS_WRITE) defines this; the default passes the text between NUL bytes to kmicro_puts and drops the
 * NULs. */
__attribute__((weak)) void kmicro_write(const char *buf, size_t n)
{
    char run[32];
    size_t k = 0;
    for (size_t i = 0; i < n; i++) {
        if (buf[i] != 0)
            run[k++] = buf[i];
        if (k > 0 && (k == sizeof run - 1u || i + 1u == n)) {
            run[k] = 0;
            kmicro_puts(run);
            k = 0;
        }
    }
}

static void put_string(const ObjHeader *s)
{
    char buf[64];
    uint32_t n = len(s);
    for (uint32_t i = 0; i < n;) {                   /* chunked: no allocation */
        uint32_t o = 0;
        while (i < n) {
            uint8_t tmp[4];
            uint32_t u = char_units(s, i, n);        /* a surrogate pair is one character, one UTF-8 sequence */
            uint32_t k = utf8_of(s, i, u, tmp, false);
            if (o + k > sizeof buf)
                break;
            memcpy(buf + o, tmp, k);
            o += k;
            i += u;
        }
        kmicro_write(buf, o);
    }
}
void Kotlin_io_Console_print(const ObjHeader *message) { put_string(message); }
void Kotlin_io_Console_println0(void) { kmicro_puts("\n"); }
void Kotlin_io_Console_println(const ObjHeader *message) { put_string(message); kmicro_puts("\n"); }
void Kotlin_io_Console_printToStdErr(const ObjHeader *message) { put_string(message); }
void Kotlin_io_Console_println0ToStdErr(void) { kmicro_puts("\n"); }
void Kotlin_io_Console_printlnToStdErr(const ObjHeader *message) { put_string(message); kmicro_puts("\n"); }

/* For the floating-point parser: the whole string as UTF-8, or false when it does not fit or holds a lone
 * surrogate (the stock runtime throws NumberFormatException for invalid text there too). */
bool km_dtoa_utf8(const ObjHeader *s, char *buf, uint32_t cap)
{
    uint32_t n = len(s);
    uint32_t need = utf8_of(s, 0, n, NULL, false);
    if (need + 1 > cap)
        return false;
    for (uint32_t i = 0; i < n; i++) {
        uint16_t c = at(s, i);
        if (c >= 0xD800 && c <= 0xDFFF) {
            if (c > 0xDBFF || i + 1 >= n || (at(s, i + 1) & 0xFC00) != 0xDC00)
                return false;
            i++;
        }
    }
    utf8_of(s, 0, n, (uint8_t *)buf, false);
    buf[need] = 0;
    return true;
}
