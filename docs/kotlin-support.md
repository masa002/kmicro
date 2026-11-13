# Kotlin® on kmicro: what works

Each row was checked by building a test program twice, for the host with the stock Kotlin/Native runtime and for
kmicro on an emulated Cortex-M4 (QEMU), and comparing the output ([tools/difftest.py](../tools/difftest.py)), or by
running it on kmicro alone where the host output naturally differs (time, memory, C interop). difftest gives kmicro
a 64 KB heap; the notes say where a feature needs more than the 16 KB default. The programs for strings,
collections, exceptions, initialisers, numbers and sequences are in [tests/diff](../tests/diff); those for the
other rows are being added there.

- **works**: behaves as on stock Kotlin/Native; for the standard library, the output is byte-identical.
- **partly**: works with the limits in the note.
- **does not work**: not yet; most of these are being fixed.
- **not applicable**: not part of Kotlin/Native either, or deprecated with an error.

This page describes Kotlin/Native 2.4.21 on the current kmicro and changes as fixes land.

| feature | status on kmicro | note |
|---|---|---|
| **Language** | | |
| classes, open/abstract, overrides, super calls, init order | works | difftest probes, also under GC stress and --size |
| interfaces with default methods/properties, diamond `super<A>.f()` | works | |
| sealed classes/interfaces, exhaustive `when`, guards in `when` | works | guards need no flag in 2.4.21 |
| data classes, `data object`, destructuring, componentN | works | |
| enum classes (entries, valueOf and its error, abstract members) | works | |
| objects, companion objects, first-use init order | works | |
| nested, inner, local, anonymous classes, object expressions | works | |
| constructors, default/named arguments, vararg and spread | works | |
| properties: custom get/set, lateinit, `by lazy` (all modes) | works | |
| delegated properties: observable, vetoable, notNull, map, provideDelegate | works | |
| class delegation (`by`) | works | |
| generics: variance, star projections, bounds, `where`, reified | works | |
| value classes | works | write `value class`; `@JvmInline` does not exist on Kotlin/Native |
| typealias, typeOf, KClass simpleName/qualifiedName, isInstance | works | |
| extension functions/properties, infix, operator overloading | works | |
| lambdas, closures, function references, fun interfaces/SAM | works | |
| inline functions, crossinline/noinline, non-local return/break/continue | works | |
| scope functions, DSL builders, buildString/buildList/buildMap | works | |
| smart casts, safe calls, elvis, `!!`, `as`/`as?` messages | works | messages as in stock Kotlin/Native |
| ranges, progressions, loops, labeled break/continue | works | |
| string templates, raw strings, `$$` multi-dollar strings | works | |
| context parameters | works | no flag needed in 2.4.21 |
| annotations, @OptIn/@RequiresOptIn, @Deprecated | works | |
| unsigned types, bitwise ops, overflow, numeric conversions | works | |
| tailrec | works | 100000 deep |
| deep recursion | does not work | no overflow detection: the stack runs through .bss and the heap, then exit 99 or a QEMU lockup |
| large constant-size local arrays | partly | placed on the stack (up to 64 KB per function); silently overwrite the heap when larger than the free stack |
| reading a non-null property before it is initialised (null read) | partly | host segfaults; kmicro reads the flash alias at 0 and throws a misleading OutOfMemoryError |
| public function with a backtick name containing spaces | does not work | fails in the C export of -p static; private/internal works |
| assert() | not applicable | not evaluated without -ea, as in stock Kotlin/Native; kbuild cannot pass -ea |
| `@CName` | does not work | compiles but exports nothing; use `--c-api` |
| unicode identifiers, long string constants | works | |
| more than ~160 top-level reference properties | does not work | 'too many globals' panic at startup; limit not configurable |
| **Exceptions** | | |
| throw/catch/finally, nested, rethrow, throw in finally, catch order | works | also under GC stress |
| standard exception messages (div by zero, index, cast, NumberFormat, lateinit, require/check) | works | byte-identical |
| cause chains, addSuppressed, `use`, Result/runCatching | works | |
| exceptions from init blocks, lazy, toString, sequences, file initializers | works | |
| stack trace of a single exception (getStackTrace, stackTraceToString) | partly | addresses only; a frame inside try repeats up to 12 times; the throwing frame can be dropped |
| printStackTrace()/stackTraceToString() with cause or suppressed | does not work | panics: Kotlin_NativePtrArray_getArrayLength |
| uncaught exception report | partly | no 'Caused by'; message cut at 95 bytes; LTO folds frames into Reset_Handler |
| setUnhandledExceptionHook | does not work | hook never runs |
| processUnhandledException | partly | prints and returns instead of terminating |
| terminateWithUnhandledException | works | |
| OutOfMemoryError | partly | catchable only for one request larger than the heap; heap exhaustion panics (stock aborts too) |
| **Coroutines** | | |
| suspend functions, lambdas, references, suspend interface members | works | |
| startCoroutine/createCoroutine, suspendCoroutine, intercepted continuations | works | |
| CoroutineContext elements, ContinuationInterceptor | works | |
| try/finally across suspension points | works | |
| sequence/iterator builders | works | |
| event loop with timers, GC while suspended | works | |
| **Memory** | | |
| garbage collection, cyclic garbage, wide graphs | works | precise non-moving mark-sweep |
| GC.collect / collectCyclic | works | |
| GC.schedule, GC.lastGCInfo | does not work | natives missing |
| WeakReference | does not work | panics: Konan_getWeakReferenceImpl |
| createCleaner | does not work | clear panic: finalizers not supported |
| @ThreadLocal objects and properties | works | |
| dead objects referenced by frame slots | partly | stay alive until the function returns; matters on a small heap |
| **Concurrency** | | |
| AtomicInt/AtomicLong/AtomicBoolean/AtomicReference (both APIs), @Volatile | works | reference CAS/exchange not atomic against interrupt handlers |
| AtomicIntArray/AtomicLongArray/AtomicArray | does not work | element-address natives missing; under qbuild a bogus IndexOutOfBoundsException |
| Worker | does not work | single-threaded runtime |
| synchronized | not applicable | not in the Kotlin/Native stdlib |
| **Collections and sequences** | | |
| List/Set/Map/ArrayDeque, all common operations and errors | works | byte-identical, also under GC stress |
| arrays of all primitive types, Array<T>, content* functions | works | |
| UIntArray/UByteArray | works | |
| sequences, generateSequence, sequence builder | works | |
| shuffle/shuffled/random on collections | does not work | needs kotlin.random |
| **Strings and text** | | |
| String functions, StringBuilder, split/replace/trim/pad | works | byte-identical |
| uppercase/lowercase, Char classification, digitToInt | works | Unicode tables copied to the heap: up to 11.7 KB kept for Char.category |
| encodeToByteArray, strict decoding | works | |
| decodeToString of truncated UTF-8 | partly | one U+FFFD per byte instead of one per sequence |
| println of a string containing U+0000 | partly | the rest of the 64-byte chunk is lost |
| Latin-1 string mode (-Xbinary=latin1Strings) | partly | implemented in the runtime, but no tool can enable it and it is untested |
| String.format | not applicable | not in the Kotlin/Native stdlib |
| **Numbers** | | |
| integer parsing, toString(radix), arithmetic, bit operations | works | byte-identical |
| Double/Float toString, rounding, toBits | works | byte-identical |
| String.toDouble/toFloat/toDoubleOrNull | partly | correct, but pulls in the Regex engine: ~27 KB peak heap (out of memory on the 16 KB default) and ~390 KB of flash; fails a board link without the regex natives |
| kotlin.math | partly | newlib libm: transcendental results can differ in the last digit |
| unsigned types: arithmetic, parsing, printing | works | |
| **Regex** | | |
| matches/find/findAll/groups/named groups/replace/split, options | works | first use keeps 12-14 KB of heap; three small patterns exhaust the 16 KB default heap; ~330 KB of flash |
| lookaround, backreferences, lazy/possessive, Unicode classes | works | heap cost as above |
| deep backtracking over long input | does not work | needs ~64 KB of stack; overflows silently |
| RegexOption.CANON_EQ | does not work | uncatchable panic: Kotlin_text_regex_decomposeString |
| **Time and random** | | |
| Duration arithmetic, toString(), parse, ISO format, toComponents | works | |
| Duration.toString(unit, decimals) | does not work | Kotlin_DurationValue_formatToExactDecimals missing |
| Random(seed), Random.Default, random(), shuffled() | does not work | panics: Kotlin_system_getSteadyTimeNanos |
| measureTime, TimeSource.Monotonic | does not work | no clock natives |
| Clock.System.now() | does not work | Kotlin_system_getSystemTimeNanos missing |
| getTimeMillis/measureTimeMillis, kotlin.native.internal.GC, @SharedImmutable | not applicable | deprecated with ERROR since 2.1 |
| **Other stdlib** | | |
| Uuid parse/toString/fromLongs/fromByteArray | works | |
| Uuid.random() | does not work | needs an entropy source |
| HexFormat, Base64 | works | |
| Pair/Triple, comparators, lazy, require/check/TODO | works | |
| kotlin.native.Platform | does not work | Konan_Platform_* missing |
| exitProcess | does not work | panics, exits 98 |
| readln/readlnOrNull | does not work | console natives missing |
| ByteArray.getIntAt/setIntAt family | does not work | Kotlin_ByteArray_*At missing |
| findAssociatedObject | does not work | native missing |
| **C interop** | | |
| calling C functions with scalars and pointers, C strings | works | |
| C globals, #define constants, enums, struct fields, sizeOf | works | |
| variadic C functions | works | |
| memScoped, usePinned/addressOf, readBytes, cValuesOf | works | |
| nativeHeap alloc/free in LIFO order | works | |
| nativeHeap freed out of order, or more than KM_INTEROP_BYTES (1 KB) | does not work | 'interop arena full' panic instead of reuse or OutOfMemoryError |
| structs by value (CValue, useContents, cValue{}) | does not work | build fails: bridges.py drops struct types |
| staticCFunction callbacks | does not work | build fails: bridges.py copies the whole program |
| header static inline functions containing loops | does not work | build fails: undefined !llvm.loop metadata |
| StableRef | does not work | ExternalRCRef natives missing |
| C calling Kotlin by plain names (--c-api) | works | names only, signatures are not checked |
| platform.posix | partly | string/printf functions work; generated for glibc: errno and usleep missing, time_t size differs from newlib |
| **Build and tools** | | |
| a Kotlin-only program with `fun main()` | does not work | needs a hand-written C driver |
| interrupt handlers written in Kotlin | works | allocation guard misses runtime-internal allocations; isr_check misses handlers aliased by --c-api unless they are named with --callback |
| --init-all | partly | file-level globals only; objects are not initialised |
| --size --hot | partly | anchored regexes never match; the count is not shown |
| board build | partly | runtime flags undocumented; programs using toDouble/Regex fail to link without the regex natives |
| Windows paths with spaces or non-ASCII characters | does not work | kotlinc-native argument file is unquoted and not UTF-8 |
| program start with an inlined floating-point main | does not work | NOCP UsageFault before the FPU is enabled |
