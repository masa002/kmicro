/* kmicro shim for the Apache Harmony floating-point conversion code in this folder: Kotlin/Native 2.4.21's copy
 * (kotlin-native/runtime/src/main/cpp/dtoa, Apache License 2.0) with the changes listed in README.md. It replaces the
 * Kotlin/Native runtime headers those files included with the few definitions they actually use. */
#ifndef KM_DTOA_SHIM_H
#define KM_DTOA_SHIM_H
#include <stdint.h>
#include <string.h>

typedef int8_t KByte;
typedef int16_t KShort;
typedef int32_t KInt;
typedef int64_t KLong;
typedef float KFloat;
typedef double KDouble;
typedef bool KBoolean;
typedef struct ObjHeader ObjHeader;
typedef ObjHeader *KRef;
typedef const ObjHeader *KConstRef;

extern "C" {
void ThrowNumberFormatException(void) __attribute__((noreturn));
void ThrowOutOfMemoryError(void) __attribute__((noreturn));
/* UTF-8 of a Kotlin string into buf (false: not valid text). Text that does not fit is cut and *e, its decimal
 * exponent, raised by the number of digits left out. */
bool km_dtoa_utf8(KConstRef s, char *buf, uint32_t cap, KInt *e);
void *km_dtoa_calloc(uint32_t n, uint32_t size);
void km_dtoa_free(void *p);
}

namespace kotlin {}                         /* the sources say "using namespace kotlin" */
/* The buffer for the digits of the text. createDouble reads at most 310 of them and createFloat 136: by then the
 * number has more bits than they keep (MAX_ACCURACY_WIDTH), and they only count the digits that follow into the
 * exponent. So km_dtoa_utf8 can leave out the digits that do not fit. */
#define KM_DTOA_BUF 400

static inline KDouble bitsToDouble(KLong bits) { KDouble d; memcpy(&d, &bits, 8); return d; }
static inline KLong doubleToBits(KDouble v) { KLong l; memcpy(&l, &v, 8); return l; }
static inline KFloat bitsToFloat(KInt bits) { KFloat f; memcpy(&f, &bits, 4); return f; }
static inline KInt floatToBits(KFloat v) { KInt i; memcpy(&i, &v, 4); return i; }

#endif
