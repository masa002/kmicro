# The compiler's 32-bit ARM target: how deprecated `linux_arm32_hfp` is, and what is left when it goes

> **Status.** Written in November 2026, with Kotlin 2.5.0-RC as the newest release. kmicro still builds on
> `linux_arm32_hfp`, and nothing below has been built or tried: the note records what the sources and the
> distributions say, so that the choice does not have to be researched on the day the target goes.

Path prefixes:
- `M/` = the github.com/JetBrains/kotlin repository at tag v2.5.0-RC (commit 4eeec3a1)
- `D24/`, `D25/` = the Kotlin/Native prebuilt distributions for Windows, 2.4.21 and 2.5.0-RC
  (`kotlin-native-prebuilt-windows-x86_64-<version>`)
- `KT-n` = a YouTrack issue read through its REST API on 2026-11-16

## 0. Key findings

- **In 2.5.0-RC the target is where it was in 2.4.21:** deprecated with a warning, compiled as before, and shipped in
  the prebuilt distribution. VERIFIED (§1).
- **No release is named for its removal.** The documentation says "deprecated and scheduled for removal" and gives
  only the start, Kotlin 1.8.20. No YouTrack issue was found that schedules it. INFERRED from the places searched
  (§1).
- **The step that ends kmicro's use is the error level, not the removal.** A target whose deprecation is an error is
  left out of the distribution: 2.5.0-RC has no libraries for `macos_x64`, `tvos_x64` and `watchos_x64`. For
  `watchosArm32`, warning, error and removal came within two feature releases (2.4.20 to 2.5.0). VERIFIED (§2).
- **`android_arm32` is the only other target with the same data layout,** and 2.5.0-RC deprecates it too. (§3, B)
- **No compiler option brings back a target the distribution does not have.** (§3, C)
- **The option that costs nothing until it is needed is to stay on the last release that has the target.** (§3, A)

## 1. Where the target stands in 2.5.0-RC

| Fact | Source |
|---|---|
| `linux_arm32_hfp` is a member of `deprecatedTargets` and of `toleratedDeprecatedTargets` | `M/native/utils/src/org/jetbrains/kotlin/konan/target/KonanTarget.kt:59-71` VERIFIED |
| The compiler prints `warning: target linux_arm32_hfp is deprecated and will be removed soon. See: https://kotl.in/native-targets-tiers` when it makes anything but a klib, and compiles. The text and the set of targets it is printed for (`softDeprecatedTargets`) are those of 2.4.21. kmicro's tools leave this one warning out of what they show (`TARGET_NOTICE` in [toolchain/kn.py](../../toolchain/kn.py)) | `M/kotlin-native/backend.native/compiler/ir/backend.native/src/org/jetbrains/kotlin/backend/konan/KonanDriver.kt:32-37, 118-121` VERIFIED; the same lines at tag v2.4.21 |
| In the Gradle plugin, a tolerated deprecated target is a warning ("Target will be removed in a future release"), and a deprecated target that is not tolerated is an error ("Compilation for this target is no longer supported") | `M/libraries/tools/kotlin-gradle-plugin-dsl-codegen/src/main/kotlin/org/jetbrains/kotlin/generators/gradle/dsl/presetEntries.kt:99-103`; `KonanTarget.kt:12-13` VERIFIED |
| The distribution has the target's runtime (`konan/targets/linux_arm32_hfp/native/*.bc`) and its platform libraries (`klib/platform/linux_arm32_hfp`), and konan.properties has the entries for it that 2.4.21 has | `D25/`, `D24/` VERIFIED |
| The documentation lists `linuxArm32Hfp` under "Deprecated targets": "The following targets are deprecated and scheduled for removal", with the deprecation start Kotlin 1.8.20 and no removal version | <https://kotlinlang.org/docs/native-target-support.html>, read 2026-11-16 VERIFIED |
| Work for the target still lands: `linuxArm32Hfp()` was added to the Power Assert runtime for 2.5.0 | KT-88322 (fixed 2026-08-31, 2.5.0-Beta1) VERIFIED |
| No issue schedules the removal: the YouTrack searches `linuxArm32Hfp` and `linux_arm32_hfp deprecated` in project KT return none | INFERRED from those two searches |

The release notes of 1.8.20 named seven targets that "have been deprecated with Kotlin 1.8.20 and will be removed in
1.9.20", `linuxArm32Hfp` among them (<https://kotlinlang.org/docs/whatsnew1820.html#update-for-kotlin-native-targets>).
Those of 1.9.20 list the six others as removed and not `linuxArm32Hfp`
(<https://kotlinlang.org/docs/whatsnew1920.html>). VERIFIED in the sources of both pages
(github.com/JetBrains/kotlin-web-site, `docs/topics/whatsnew/whatsnew1820.md` and `whatsnew1920.md`). So the one
removal date ever published has passed, and the target has stayed at the warning level since.

## 2. What the next levels look like

In 2.5.0 (read from 2.5.0-RC) other targets take the steps `linux_arm32_hfp` has not taken:

| Target | Deprecated (warning) | Error | Removed |
|---|---|---|---|
| `macosX64`, `tvosX64`, `watchosX64` | 2.3.20 | 2.5.0 (KT-84955) | not yet |
| `watchosArm32` | 2.4.20 | 2.5.0 (KT-87513) | 2.5.0 (KT-78078): the name is kept only to report the error |
| `linuxArm32Hfp` | 1.8.20 | not yet | not yet |
| `androidNativeArm32`, `Arm64`, `X86`, `X64` | 2.5.0 (new in `deprecatedTargets`; tolerated) | not yet | not yet |

Sources: the documentation page of §1 for the start versions; `KonanTarget.kt` for the sets (58-59 at tag v2.4.21,
59-71 at v2.5.0-RC);
`M/kotlin-native/build-tools/src/main/kotlin/org/jetbrains/kotlin/konan/target/EnabledTargets.kt:12-22`. VERIFIED.

What the error level means for a tool that runs the compiler directly, as kmicro does:

- `enabledTargets()` in EnabledTargets.kt leaves out every target that is deprecated and not tolerated.
  `D24/klib/platform` has `macos_x64`, `tvos_x64`, `watchos_arm32` and `watchos_x64`; `D25/klib/platform` has none of
  them. VERIFIED (the two folder listings). That this function is what decides the content of the distribution is
  INFERRED.
- So the release that raises `linux_arm32_hfp` to an error is expected to ship without
  `konan/targets/linux_arm32_hfp` and `klib/platform/linux_arm32_hfp`, and `kotlinc-native -target linux_arm32_hfp`
  then has no runtime bitcode to take its types and declarations from. INFERRED.
- The warning can become an error in the next feature release: for `watchosArm32` the warning
  came in 2.4.20 and the error and the removal in 2.5.0.

The weekly CI job `next-kotlin` builds with the newest pre-release, so it fails at the first Beta that takes the step,
some weeks before the release.

## 3. The options when it goes

### A. Stay on the last Kotlin/Native release that has the target

kmicro reads the IR of one compiler version anyway ([roadmap.md](../roadmap.md#compiler-versions)).

- Cost: no newer language version and no newer standard library for kmicro programs; libraries published only for
  newer compilers cannot be used. Nothing to build.
- It depends on two downloads staying available: the release archive on github.com/JetBrains/kotlin (old releases
  are still there) and the compiler's dependencies, which the first compile fetches from `dependenciesUrl`
  (`D25/konan/konan.properties:18`, `https://download.jetbrains.com/kotlin/native`): the LLVM and the Linux ARM
  sysroot `arm-unknown-linux-gnueabihf-gcc-8.3.0-glibc-2.12.1-kernel-4.9-1`. A copy of `~/.konan/dependencies`
  removes the second dependency. INFERRED that both stay online.

### B. `android_arm32`

The only other target of 2.5.0-RC with a 32-bit ARM architecture (`Architecture.ARM32`,
`KonanTarget.kt:19, 38`; `watchos_arm32` is removed).

- Its triple is `arm-unknown-linux-androideabi` (`D25/konan/konan.properties:630`). clang gives that triple the data
  layout of `linux_arm32_hfp` and of the Cortex-M targets, `e-m:e-p:32:32-Fi8-i64:64-v128:64:128-a:0:32-n32-S64`.
  VERIFIED with the compiler's clang:
  `echo 'void f(void){}' | clang --target=arm-unknown-linux-androideabi -S -emit-llvm -x c - -o -`.
  (`watchos_arm64` is ILP32 on AArch64 with another layout, `e-m:o-p:32:32-...-i64:64-i128:128-n32:64-S128`, and
  `android_x86` aligns `double` to 4 bytes: neither can stand in.)
- It differs where kmicro has to look again, all INFERRED from konan.properties, nothing tried:
  - the calling convention is soft-float (`targetCpu` arm7tdmi, features `+armv4t ... -fpregs`, line 631-632), where
    `linux_arm32_hfp` is hard-float. The Kotlin IR names no calling convention, but the C stubs of cinterop are
    written for the target's: [toolchain/aapcs.py](../../toolchain/aapcs.py) rewrites struct results for cores
    without an FPU today and would have to do the opposite for cores with one;
  - `clangFlags` add `-femulated-tls -mrelocation-model pic` (line 633);
  - the platform libraries are those of Android (Bionic), 14 klibs instead of 5, and the standard library takes its
    Android branches (`Platform.osFamily`, logging);
  - the first compile downloads the Android NDK sysroot and toolchain dependencies.
- It is deprecated since 2.5.0 itself, at the warning level (§2), and the documentation, which does not say so yet,
  has it in Tier 3: "not in active development". It may not outlive `linux_arm32_hfp` by much.
- Cost: the checks of a new compiler version (the runtime contract, retarget.py, run_all, difftest), plus the
  differences above. No build of the compiler.

### C. A compiler option

- `-Xoverride-konan-properties=key=value;...` replaces entries of konan.properties for a target that exists: its
  triple, CPU, features, clang flags (`M/kotlin-native/HACKING.md:310`). VERIFIED that the option exists and what it
  is documented for.
- It cannot add a target. The targets are the objects of the sealed class `KonanTarget`, each with a fixed
  `Architecture` (`KonanTarget.kt:16-38`), and the compiler takes the runtime's types and declarations from the
  target's bitcode files in `konan/targets/<target>/native`, which the distribution does not have for a removed
  target. Overriding the triple of a 64-bit target does not make its IR 32-bit. INFERRED from those files, not tried.
- Cost: none, and no result.

### D. Build the distribution from source, with the target kept

The compiler is Apache-2.0 and builds from the repository: `./gradlew :kotlin-native:dist` makes the compiler and
the standard library for the host, `:kotlin-native:bundle` for all targets (`M/kotlin-native/README.md`, "To compile
the basic compiler distribution from sources"). VERIFIED that the commands are documented.

- While the target is only excluded (error level), the change is to make it tolerated again in `KonanTarget.kt` and
  to build. After the removal it is a patch that restores what the removal took out: the `KonanTarget` object, the
  konan.properties block, the clang arguments (`ClangArgs.kt:132`), the target in the runtime's build. The removal of
  `watchos_arm32` (KT-78078) shows which files such a patch touches. INFERRED.
- Cost: a build of the Kotlin repository for every compiler version kmicro supports (a JDK and the repository's own
  toolchains; the time and the disk space it takes were not measured), a patch that is rebased on every release,
  binaries that kmicro would have to publish for its users or ask them to build. kmicro would no longer run the
  official compiler unmodified, which is what [how-it-works.md](../how-it-works.md) starts from.

### Not options

- **64-bit ARM IR** (`linux_arm64`): another data layout, 64-bit pointers in every object
  ([roadmap.md](../roadmap.md#targets), "64-bit ARM").
- **Kotlin/Wasm:** `wasm32` has 32-bit pointers, but that compiler has its own backend (`M/compiler/ir/backend.wasm`)
  and produces Wasm with garbage-collected references, not LLVM IR. INFERRED.

## 4. What follows for kmicro

Nothing has to change now. The order in which the options cost more is A, B, D. A needs no preparation beyond a
copy of the dependencies. B can be measured cheaply while `linux_arm32_hfp` still exists, by comparing the IR of one
program for both targets, and is worth that measurement only if `android_arm32` is still at the warning level when
`linux_arm32_hfp` leaves it.
