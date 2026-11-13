# hello

The smallest kmicro program: C starts the runtime and calls one Kotlin function by a plain C name.

| File | |
|---|---|
| `hello.kt` | the Kotlin function, package `hello` |
| `hello.h` | its C prototype: `int32_t hello(int32_t times)` |
| `main.c` | starts the runtime, calls `hello(3)` |

Run it on the emulator (`-v` shows the build and the program's output; without it, run_all prints one PASS line):

```
python tests/run_all.py -v hello
```

It does the same as these two commands:

```
python tools/kbuild.py build/t/hello examples/hello/hello.kt --c-api examples/hello/hello.h --package hello
python tools/qbuild.py build/t/hello/hello.elf examples/hello/main.c build/t/hello/k.o --run
```

The program prints, after the lines of the build:

```
Hello from Kotlin #1, Kotlin #2, Kotlin #3 on a bare Cortex-M4
```

`--c-api hello.h --package hello` gives the Kotlin function `hello.hello` the C name `hello`. Prototypes in
snake_case map to camelCase functions: `int32_t gc_chains(int32_t)` calls `fun gcChains(rounds: Int): Int`.
