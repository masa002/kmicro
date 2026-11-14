# Kotlin® on kmicro: what works

Each row was checked by building a test program twice, for the host with the stock Kotlin/Native runtime and for
kmicro on an emulated Cortex-M4 (QEMU), and comparing the output ([tools/difftest.py](../tools/difftest.py)), or by
running it on kmicro alone where the host output naturally differs (time, memory, C interop). The kmicro side runs
on the default 16 KB heap; a program that needs more says so, with the reason, in a `// difftest: heap` line, and the
notes below give the costs. The programs are in [tests/diff](../tests/diff); the `d_known_*.kt` ones show what does
not work and run only when named.

- **works**: behaves as on stock Kotlin/Native; for the standard library, the output is byte-identical.
- **partly**: works with the limits in the note.
- **does not work**: fails as the note says.
- **not supported**: left out by design (it needs threads or an OS); the note says what happens instead.
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
| deep recursion | partly | no StackOverflowError: on the qemu-l475 target an MPU guard below the stack stops the program with 'kmicro fault: stack overflow' (exit 99); a board needs the same guard, 4 KB there: larger than any frame of the runtime (1024 B) and of the standard library (2984 B, `Regex`), so only a larger frame of the program could step over it |
| large constant-size local arrays | partly | placed on the stack (up to 64 KB per function); kbuild warns above 512 B (`--stack-array-limit`, `--stack-array-error`); `tools/frames.py` shows the largest frames |
| reading a non-null property before it is initialised (null read) | partly | the host segfaults; on qemu-l475 kmicro stops with 'kmicro fault: null pointer access' (exit 99), not a catchable exception |
| public function with a backtick name containing spaces | does not work | the C export of -p static fails, and kbuild names the cause; private/internal works |
| assert() | not applicable | not evaluated without -ea, as in stock Kotlin/Native |
| `@CName` | works | same type rules as `--c-api`: primitives, unsigned numbers and pointers |
| unicode identifiers, long string constants | works | |
| many top-level reference properties | works | more than `KM_GLOBALS` (160) needs `-D KM_GLOBALS=N` for the runtime; the panic names the macro |
| **Exceptions** | | |
| throw/catch/finally, nested, rethrow, throw in finally, catch order | works | also under GC stress |
| standard exception messages (div by zero, index, cast, NumberFormat, lateinit, require/check) | works | byte-identical |
| cause chains, addSuppressed, `use`, Result/runCatching | works | |
| exceptions from init blocks, lazy, toString, sequences, file initializers | works | |
| stack trace of a single exception (getStackTrace, stackTraceToString) | partly | addresses, at most 12 frames; `tools/symbolize.py` names them (with file:line under `-g`); LTO folds inlined functions into their callers |
| printStackTrace()/stackTraceToString() with cause or suppressed | works | |
| uncaught exception report | partly | the whole message and every 'Caused by'; suppressed exceptions and custom toString() are left out |
| setUnhandledExceptionHook | works | not for an exception that escapes an interrupt handler; the C hook `kmicro_on_uncaught` runs in every case |
| processUnhandledException | works | |
| terminateWithUnhandledException | works | |
| OutOfMemoryError | partly | catchable only for one request larger than the heap; heap exhaustion stops the program with a report (stock aborts too) |
| **Coroutines** | | |
| suspend functions, lambdas, references, suspend interface members | works | |
| startCoroutine/createCoroutine, suspendCoroutine, intercepted continuations | works | |
| CoroutineContext elements, ContinuationInterceptor | works | |
| try/finally across suspension points | works | |
| sequence/iterator builders | works | |
| event loop with timers, GC while suspended | works | |
| **Memory** | | |
| garbage collection, cyclic garbage, wide graphs | works | precise non-moving mark-sweep |
| GC.collect / collectCyclic | works | not inside an interrupt handler |
| GC.schedule, GC.lastGCInfo | partly | GC.schedule collects at once (and does nothing inside an interrupt handler); lastGCInfo is always null |
| GC heap tuning (autotune, targetHeapBytes, ...), Debugging.dumpMemory, ImmutableBlob, MemoryUsageInfo.peakResidentSetSizeBytes, the settings of GC.MainThreadFinalizerProcessor | not supported | the program stops with '... is not supported on kmicro'; GC.MainThreadFinalizerProcessor.available is false |
| WeakReference | not supported | the program stops with '... is not supported on kmicro' |
| createCleaner | not supported | the program stops with 'finalizers (Cleaner, WeakReference) are not supported' |
| @ThreadLocal objects and properties | works | |
| dead objects referenced by frame slots | partly | stay alive until the function returns; matters on a small heap |
| **Concurrency** | | |
| AtomicInt/AtomicLong/AtomicBoolean/AtomicReference (both APIs), @Volatile | works | also atomic against interrupt handlers, reference CAS and exchange included |
| AtomicIntArray/AtomicLongArray/AtomicArray | works | |
| Worker | not supported | single-threaded runtime: the program stops with '... is not supported on kmicro' |
| synchronized | not applicable | not in the Kotlin/Native stdlib |
| **Collections and sequences** | | |
| List/Set/Map/ArrayDeque, all common operations and errors | works | byte-identical, also under GC stress |
| arrays of all primitive types, Array<T>, content* functions | works | |
| UIntArray/UByteArray | works | |
| sequences, generateSequence, sequence builder | works | |
| shuffle/shuffled/random on collections | works | |
| **Strings and text** | | |
| String functions, StringBuilder, split/replace/trim/pad | works | byte-identical |
| uppercase/lowercase, Char classification, digitToInt | works | the Unicode tables stay in flash; Char.category creates its 30 entries (984 B) |
| encodeToByteArray, strict decoding | works | |
| decodeToString of invalid or truncated UTF-8 | works | |
| println of a string containing U+0000 | partly | the default `kmicro_write` drops the U+0000 itself and prints the rest; a board's `kmicro_write` gets it |
| Latin-1 string mode (-Xbinary=latin1Strings) | partly | `kbuild.py --kotlinc -Xbinary=latin1Strings=true` enables it; one test, `strings_latin1`, runs the string checks of run_all in this mode, difftest does not use it |
| String.format | not applicable | not in the Kotlin/Native stdlib |
| **Numbers** | | |
| integer parsing, toString(radix), arithmetic, bit operations | works | byte-identical |
| Double/Float toString, rounding, toBits | works | byte-identical |
| String.toDouble/toFloat/toDoubleOrNull | works | no Regex engine; runs on the 16 KB default heap |
| kotlin.math | partly | newlib libm: results within 2 ulp of stock |
| unsigned types: arithmetic, parsing, printing | works | |
| **Regex** | | |
| matches/find/findAll/groups/named groups/replace/split, options | works | the first pattern keeps 11.5 KB of the heap and three small ones need a 20 KB heap; a program that uses Regex is about 366 KB of flash (235 KB with `--size`) ([costs](writing-kotlin.md#memory)) |
| lookaround, backreferences, lazy/possessive, Unicode classes | works | `\p{L}` alone runs on the 16 KB heap (13.4 KB kept); about 30 patterns created in one function run out of memory even at 64 KB (`d_known_regex_heap`) |
| deep backtracking over long input | does not work | needs ~64 KB of stack; stops with 'kmicro fault: stack overflow' (exit 99) |
| RegexOption.CANON_EQ | not supported | throws IllegalArgumentException: 'RegexOption.CANON_EQ is not supported on kmicro' |
| **Time and random** | | |
| Duration arithmetic, toString(), parse, ISO format, toComponents | works | |
| Duration.toString(unit, decimals) | works | |
| Random(seed), Random.Default, random(), shuffled() | works | Random.Default takes its seed from the board hook `kmicro_random_seed` (the QEMU targets seed it from the clock); without one it repeats after every reset |
| measureTime, TimeSource.Monotonic | works | through the board hook `kmicro_time_ns` (the QEMU targets have it); without it the program stops naming the hook |
| Clock.System.now() | works | through the board hook `kmicro_wall_time_ns` (the QEMU targets have it) |
| getTimeMillis/measureTimeMillis, kotlin.native.internal.GC, @SharedImmutable | not applicable | deprecated with ERROR since 2.1 |
| **Other stdlib** | | |
| Uuid parse/toString/fromLongs/fromByteArray | works | |
| Uuid.random() | partly | needs the board hook `kmicro_random_bytes` (a hardware random number generator); without it, as on QEMU, the program stops naming the hook |
| HexFormat, Base64 | works | |
| Pair/Triple, comparators, lazy, require/check/TODO | works | |
| kotlin.native.Platform | works | osFamily UNKNOWN, cpuArchitecture ARM32, isLittleEndian true, canAccessUnaligned false, isDebugBinary false, getAvailableProcessors() 1, programName null |
| exitProcess | works | calls the board's `kmicro_exit(status)` |
| readln/readlnOrNull | works | through the board hook `kmicro_getc`; without it the input is empty |
| ByteArray.getIntAt/setIntAt family | works | |
| findAssociatedObject | works | |
| **C interop** | | |
| calling C functions with scalars and pointers, C strings | works | `kbuild.py --def FILE.def` runs cinterop |
| C globals, #define constants, enums, struct fields, sizeOf | works | |
| variadic C functions | works | |
| memScoped, usePinned/addressOf (on a String too), readBytes, cValuesOf, vectorOf | works | `d_natives` |
| nativeHeap alloc/free in any order | works | freed blocks are reused and merged with their neighbours |
| native memory beyond `KM_INTEROP_BYTES` (1 KB) | partly | throws OutOfMemoryError; raise the arena with `-D KM_INTEROP_BYTES=N` |
| structs by value (CValue, useContents, cValue{}) | works | [tests/cinterop_shapes](../tests/cinterop_shapes) |
| staticCFunction callbacks | works | an exception thrown inside one does not reach a Kotlin try around the C call, as on stock: catch it in the callback |
| header static inline functions, with loops, inline assembly or restrict pointers | works | |
| StableRef | works | at most `KM_STABLE_REFS` (16) live at once |
| C calling Kotlin by plain names (--c-api) | works | the prototypes are checked against the Kotlin functions |
| platform.posix | partly | string/printf functions work; generated for glibc: errno and usleep missing, time_t size differs from newlib |
| **Build and tools** | | |
| a Kotlin-only program with `fun main()` | works | link [targets/common/kotlin_main.c](../targets/common/kotlin_main.c) as the C main |
| interrupt handlers written in Kotlin | works | the allocation guard covers the runtime's own allocations and collections; isr_check reads the vector table; [examples/irq](../examples/irq) |
| --init-all | works | file-level globals, objects, companions and sub-packages |
| --size --hot | works | |
| board build | works | [porting.md](porting.md): the board contract, start-up, runtime flags, linker script and libraries; [examples/selftest/stm32l431](../examples/selftest/stm32l431) is a complete one |
| Windows paths with spaces or non-ASCII characters | partly | folders work; a file name outside the ANSI code page fails in the xPack tools |
| program start with an inlined floating-point main | works | |
