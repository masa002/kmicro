# Contributing to kmicro

Bug reports, fixes, tests and documentation are welcome. A report with a small program that shows the problem
helps most; a fix comes with a test that fails without it.

## Tools and build

[BUILDING.md](BUILDING.md) lists the tools (Kotlin/Native 2.4.21 and the Java to run it, the LLVM that Kotlin/Native
downloads, the xPack Arm GCC and QEMU, Python 3.10 or later) and where kmicro looks for them.
`python toolchain/paths.py` shows what it found. The Python scripts use only the standard library.

A program is built with kbuild and linked and run on QEMU's emulated STM32L475 with qbuild:

```
python tools/kbuild.py build/app app.kt
python tools/qbuild.py build/app/app.elf targets/common/kotlin_main.c build/app/k.o --run
```

[docs/how-it-works.md](docs/how-it-works.md) explains the pipeline and the runtime, and
[docs/porting.md](docs/porting.md) the build for a board.

## Tests

Three suites, all on the host and QEMU; no hardware is needed.

- **`python tests/run_all.py [NAME ...]`** builds the test programs and the examples, runs them on QEMU and compares
  each program's whole output with `tests/expected/<name>.txt`. With names it runs only those; `--stress` collects
  garbage at every allocation, `--kotlin` recompiles the Kotlin code even when its saved IR is current, and `-v`
  prints the build messages and the program's output. A test also fails when its image does not fit the STM32L431
  (256 KB of flash, 64 KB of RAM) and the test is not marked large.

  ```
  $ python tests/run_all.py selftest
  PASS  selftest                     flash 129.9 KB  RAM 18.4 KB, isr_check, isr_check_boxing
  1 passed, 0 failed
  ```

- **`python tools/difftest.py [NAME ...]`** builds each program in `tests/diff/` twice, for the host with the stock
  Kotlin/Native runtime and for kmicro on QEMU, and requires the same output. `--stress` collects garbage at every
  allocation on the kmicro side, and `--size` builds it as `kbuild.py --size` does. Without names it runs every
  program but the `d_known_*` ones, which show what does not work and run only when named. Without `--stress` the
  heap peak in the report is often the heap size; with it, the peak is the most the program had live at once.

  ```
  $ python tools/difftest.py d_strings
  kotlinc-native: compiling 1 file...
  single-core: 126 init-state loads made plain
  SAME  d_strings  (1644 bytes, 30 lines, qemu exit 0)  flash 164.3 KB  RAM 18.5 KB  heap 16384: peak 16360 live 376
  1 same, 0 different
  ```

- **`python -m unittest discover -s tests/unit`** tests the build tools, and ends with `OK` when all pass. Some of
  the tests run clang and the xPack GCC tools.

Run what your change can affect: for the runtime, `run_all.py` and `difftest.py`, both also with `--stress`; for a
tool, the unit tests and the commands of the tool that changed. Each Kotlin program is compiled by kotlinc-native
once; later runs reuse its IR until a source, an option or the compiler changes.

**A differential test** is a Kotlin file `tests/diff/d_<topic>.kt` with a `fun main()` that prints what it checks.
difftest finds it by its name. When the kmicro side needs more than the default 16 KB heap, or more flash or RAM than
the STM32L431 has, or when its numbers may differ from the host's in the last digits, the file says so on a comment
line of its own, with the reason:

```kotlin
// difftest: heap 32768 -- main keeps every object of the test alive until it returns
// difftest: large -- most of the String API in one program
// difftest: ulp 2 -- kotlin.math is newlib's libm on kmicro and another libm on the host
```

A program that shows a feature that does not work is named `d_known_<topic>.kt`; it runs only when named.

**A test for run_all** is an entry in `TESTS` in `tests/run_all.py`: its Kotlin sources (a file or a folder under
`tests/`), its C driver (or `targets/common/kotlin_main.c` for `fun main()`) and its exit code. Run it, read
`build/t/<name>/run.log` and copy that to `tests/expected/<name>.txt`, with `{N}` where a number may vary.

CI ([.github/workflows/ci.yml](.github/workflows/ci.yml)) runs the unit tests, `run_all.py` and `run_all.py --stress`
on every pull request, and difftest with and without `--stress` on main and once a week. A weekly job runs the unit
tests and `run_all.py` with the newest Kotlin release; it may fail, and that fails nothing else.

## Documentation

Docs describe the code as it is now. Every number in them is measured on the current code, and says on what (QEMU's
STM32L475, `qemu-an386`, or a board); every command shown has been run as written, with its real output. A known gap
is described as it behaves today, without a date.

## Commits and pull requests

- One change per commit. The first line says what the commit does, in the imperative, in at most 72 characters;
  after a blank line, a short body says what changed and why. The last line is `Fixes #N` for the issue it fixes, or
  `Refs #N` for one it only helps.
- Code follows the file around it: lines of at most 120 characters, comments that say why.
- A pull request goes to `main`, says what it changes and how it was tested, and is squash-merged.

## License

kmicro is licensed under the Apache License 2.0 ([LICENSE](LICENSE)). A contribution you submit is licensed under
the same terms, as section 5 of the license says, unless you state otherwise. Code taken from elsewhere must carry a
license that allows this, and its origin goes in [NOTICE](NOTICE) and in the file's first comment.

## Reporting a bug

Open an issue with the bug report form. It asks for:

- the kmicro commit (`git rev-parse --short HEAD`);
- the Kotlin/Native version and the other tools (`python toolchain/paths.py` prints them);
- the host operating system;
- the program: the Kotlin code and, if there is one, the C driver, as small as it can be;
- the commands you ran, and their full output, exit code included.

For a Kotlin feature that does not work, use the feature form, and quote the message the program stopped with, such
as `kmicro panic: ... is not supported on kmicro` or `kmicro panic: unimplemented runtime symbol: ...`.

A security problem goes to the maintainer privately: see [SECURITY.md](SECURITY.md).
