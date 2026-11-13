# runtime/dtoa

`Double` and `Float` to and from `String`: the Kotlin/Native copy of the Apache Harmony conversion code, from
`kotlin-native/runtime/src/main/cpp/dtoa` at Kotlin/Native 2.4.21 (Apache License 2.0; the notices of both projects
are in [NOTICE](../../NOTICE)).

`cbigint.cpp`, `fltconst.h` and `hycomp.h` are unchanged. The kmicro authors changed three files in 2026, and each of
them says so below its license header:

| File | Change |
|---|---|
| `dblparse.cpp`, `fltparse.cpp` | The Kotlin/Native runtime headers are replaced by `km_dtoa_shim.h`; `std::calloc` and `std::free` by `km_dtoa_calloc` and `km_dtoa_free`. The Kotlin string is converted to UTF-8 in a fixed buffer (`km_dtoa_utf8`) instead of a `std::string`, without C++ exceptions. |
| `cbigint.h` | `#include "../Types.h"` is replaced by `#include "km_dtoa_shim.h"`. |

`km_dtoa_shim.h` is kmicro's own file: the few definitions from the Kotlin/Native runtime headers that the code uses.
[tools/port_dtoa.py](../../tools/port_dtoa.py) makes the changes; run on fresh copies of the upstream files, it
reproduces this folder.

The rest of this file is the Kotlin/Native README for the folder, unchanged.

---

This is code for handling conversions between floating point and strings.
Adapted from Apache Harmony.
The code is split between C++ and Kotlin. This is the C++ part.
For kotlin part look in `kotlin-native/runtime/src/main/kotlin/kotlin/native/internal` for
`NumberConverter.kt` and `FloatingPointParser.kt`

Original source code: https://github.com/apache/harmony/tree/trunk/classlib/modules/luni/src/main/native/luni/shared
For `hycomp.h` it's https://github.com/apache/harmony/blob/trunk/classlib/modules/portlib/src/main/native/include/shared/hycomp.h

The only relevant change is: JNI is replaced with K/N runtime-specific interop.
