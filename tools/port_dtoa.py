"""Port the Kotlin/Native copy of the Apache Harmony floating-point conversion code to kmicro (runtime/dtoa).

usage: python tools/port_dtoa.py [DIR]          (default: runtime/dtoa)

A one-time porting script, kept to document the port and to repeat it. runtime/dtoa holds its result: the files of
kotlin-native/runtime/src/main/cpp/dtoa at Kotlin/Native 2.4.21, of which it changes three. Run on fresh copies of
those upstream files, it reproduces runtime/dtoa (with LF line endings); a file it has already ported is left alone.
Every replacement is literal and checked:

    dblparse.cpp, fltparse.cpp  the Kotlin/Native runtime headers are replaced by km_dtoa_shim.h; std::calloc and
                                std::free by km_dtoa_calloc and km_dtoa_free; the Kotlin string is converted to UTF-8
                                in a fixed buffer (km_dtoa_utf8) instead of a std::string, without C++ exceptions
    cbigint.h                   #include "../Types.h" is replaced by #include "km_dtoa_shim.h"

Each changed file gets a notice below its license header that says what changed.
"""
import sys
from pathlib import Path

D = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent.parent / 'runtime/dtoa'

LICENSE_END = ' *  limitations under the License.\n */\n'

PARSE_OLD = """  std::string utf8;
  try {
    utf8 = kotlin::to_string<KStringConversionMode::CHECKED>(s);
  } catch (...) {
    /* Illegal string. */
    ThrowNumberFormatException();
  }
  const char *str = utf8.c_str();"""
PARSE_NEW = """  char utf8[KM_DTOA_BUF];                       /* kmicro: no std::string, no C++ exceptions */
  if (!km_dtoa_utf8(s, utf8, sizeof utf8, &e))
    ThrowNumberFormatException();
  const char *str = utf8;"""

INCLUDES = ['#include <string>\n', '#include "../Exceptions.h"\n', '#include "../KString.h"\n',
            '#include "../Natives.h"\n', '#include "../Porting.h"\n', '#include "utf8.h"\n',
            '#include "../DoubleConversions.h"\n', '#include "../Types.h"\n']

NOTICE_PARSE = """
/*
 * Modified for kmicro by the kmicro authors, 2026. This is kotlin-native/runtime/src/main/cpp/dtoa/{name}
 * of Kotlin/Native 2.4.21 with these changes (tools/port_dtoa.py):
 *   - the Kotlin/Native runtime headers are replaced by km_dtoa_shim.h;
 *   - std::calloc and std::free are replaced by km_dtoa_calloc and km_dtoa_free;
 *   - the Kotlin string is converted to UTF-8 in a fixed buffer (km_dtoa_utf8) instead of a std::string,
 *     without C++ exceptions.
 */
"""
NOTICE_CBIGINT = """
/*
 * Modified for kmicro by the kmicro authors, 2026. This is kotlin-native/runtime/src/main/cpp/dtoa/cbigint.h
 * of Kotlin/Native 2.4.21 with #include "../Types.h" replaced by #include "km_dtoa_shim.h"
 * (tools/port_dtoa.py).
 */
"""


def add_notice(s, notice, name):
    assert s.count(LICENSE_END) >= 1, name
    return s.replace(LICENSE_END, LICENSE_END + notice, 1)


def port_parser(s, name):
    first = True
    for inc in INCLUDES:
        if inc in s:
            s = s.replace(inc, '#include "km_dtoa_shim.h"\n' if first else '', 1)
            first = False
    assert s.count(PARSE_OLD) == 1, name
    s = s.replace(PARSE_OLD, PARSE_NEW)
    s = s.replace('std::calloc(', 'km_dtoa_calloc(').replace('std::free(', 'km_dtoa_free(')
    return add_notice(s, NOTICE_PARSE.format(name=name), name)


def port_cbigint(s, name):
    assert s.count('#include "../Types.h"\n') == 1, name
    s = s.replace('#include "../Types.h"\n', '#include "km_dtoa_shim.h"\n')
    return add_notice(s, NOTICE_CBIGINT, name)


for name, port in [('dblparse.cpp', port_parser), ('fltparse.cpp', port_parser), ('cbigint.h', port_cbigint)]:
    p = D / name
    s = p.read_text(encoding='utf-8')
    if 'km_dtoa_shim.h' in s:
        continue
    p.write_text(port(s, name), encoding='utf-8', newline='\n')
    print('ported', name)
