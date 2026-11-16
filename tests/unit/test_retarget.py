# Copyright 2026 the kmicro authors (NOTICE).
# SPDX-License-Identifier: Apache-2.0
"""toolchain/retarget.py on a small IR module shaped like kotlinc-native's output: the target attributes equal clang's
for paths.target_flags(), --no-tls, --single-core, --hot, and the stdlib rewrites (Random seed, hex float parser, Unicode
tables, box functions). The output must compile with clang.

usage: python -m unittest discover tests/unit       (skipped when the LLVM of Kotlin/Native is not installed)
"""
import re
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'toolchain'))
import paths  # noqa: E402

HAVE_CLANG = paths._find(paths.llvm.env, paths.llvm.patterns, paths.llvm.what) is not None
OUT = ROOT / 'build/unit/retarget'

MODULE = r'''target datalayout = "e-m:e-p:32:32-Fi8-i64:64-v128:64:128-a:0:32-n32-S64"
target triple = "armv6kz-unknown-linux-gnueabihf"

@1 = internal unnamed_addr constant [4 x i32] [i32 1, i32 2, i32 3, i32 4]
@"kvar:kotlin.text.rangeStart#internal" = internal global ptr null
@"kvar:demo.copied#internal" = internal global ptr null
@"state_global$demo" = internal global i32 0, align 4
@"state_thread_local$demo" = internal thread_local global i32 0, align 4

define void @"kfun:state#touch(){}"() #0 {
entry:
  %0 = load atomic i32, ptr @"state_global$demo" acquire, align 4
  store i32 %0, ptr @"state_thread_local$demo", align 4
  ret void
}

define internal void @"kfun:kotlin.text.$init_global$_CharCategories.kt#internal"() #0 {
entry:
  %0 = alloca ptr, align 4
  %1 = call ptr @"kfun:kotlin.collections#copyOf__at__kotlin.IntArray(){}kotlin.IntArray"(ptr @1, ptr %0)
  store ptr %1, ptr @"kvar:kotlin.text.rangeStart#internal", align 4
  ret void
}

define void @"kfun:demo#copy(){}"() #0 {
entry:
  %0 = alloca ptr, align 4
  %1 = call ptr @"kfun:kotlin.collections#copyOf__at__kotlin.IntArray(){}kotlin.IntArray"(ptr @1, ptr %0)
  store ptr %1, ptr @"kvar:demo.copied#internal", align 4
  ret void
}

declare ptr @"kfun:kotlin.collections#copyOf__at__kotlin.IntArray(){}kotlin.IntArray"(ptr, ptr) #0

define internal void @"kfun:kotlin.random.NativeRandom.<init>#internal"(ptr %this) #0 {
entry:
  %seed = call i64 @Kotlin_system_getSteadyTimeNanos()
  store i64 %seed, ptr %this, align 8
  ret void
}

define i64 @"kfun:demo#now(){}kotlin.Long"() #0 {
entry:
  %t = call i64 @Kotlin_system_getSteadyTimeNanos()
  ret i64 %t
}

declare i64 @Kotlin_system_getSteadyTimeNanos() #0

define internal void @"kfun:kotlin.native.internal.HexStringParser.Companion.<init>#internal"(ptr %0) #0 {
entry:
  store i32 11, ptr %0, align 4
  ret void
}

define double @"kfun:kotlin.native.internal.HexStringParser.Companion#parseDouble(kotlin.String){}kotlin.Double"(ptr %0, ptr %1) #0 {
entry:
  %r = call double @"kfun:demo#regexParse(kotlin.String){}kotlin.Double"(ptr %1)
  ret double %r
}

define float @"kfun:kotlin.native.internal.HexStringParser.Companion#parseFloat(kotlin.String){}kotlin.Float"(ptr %0, ptr %1) #0 {
entry:
  %r = call double @"kfun:demo#regexParse(kotlin.String){}kotlin.Double"(ptr %1)
  %f = fptrunc double %r to float
  ret float %f
}

declare double @"kfun:demo#regexParse(kotlin.String){}kotlin.Double"(ptr) #0

define i32 @"kfun:demo#fast(kotlin.Int){}kotlin.Int"(i32 %0) #0 {
entry:
  ret i32 %0
}

define ptr @"kfun:demo#first(){0\C2\A7<kotlin.Any?>}0:0"(ptr %0) #0 {
entry:
  ret ptr %0
}

define void @bridge() {
entry:
  ret void
}

define ptr @"kfun:kotlin#<Int-box>(kotlin.Int){}kotlin.Any"(i32 %0, ptr %1) #0 {
entry:
  ret ptr %1
}

define ptr @"kfun:kotlin#<ULong-box>(kotlin.ULong){}kotlin.Any"(i64 %0, ptr %1) #0 personality ptr @bridge {
entry:
  ret ptr %1
}

define ptr @"kfun:kotlin#<Char-box>(kotlin.Char){}kotlin.Any"(i16 zeroext %0, ptr %1) #0 {
entry:
  ret ptr %1
}

define ptr @"kfun:app#boxed(kotlin.Int){}kotlin.Any"(i32 %0, ptr %1) #0 {
entry:
  %2 = call ptr @"kfun:kotlin#<Int-box>(kotlin.Int){}kotlin.Any"(i32 %0, ptr %1)
  ret ptr %2
}

attributes #0 = { "target-cpu"="arm1176jzf-s" "target-features"="+armv6kz,+dsp,+vfp2" }
attributes #1 = { }
'''

# The same rewrites on functions that carry debug information (kotlinc-native -g).
DEBUG_MODULE = r'''target datalayout = "e-m:e-p:32:32-Fi8-i64:64-v128:64:128-a:0:32-n32-S64"
target triple = "armv6kz-unknown-linux-gnueabihf"

@1 = internal unnamed_addr constant [4 x i32] [i32 1, i32 2, i32 3, i32 4]
@"kvar:kotlin.text.rangeStart#internal" = internal global ptr null

define void @bridge() !dbg !10 {
entry:
  ret void, !dbg !11
}

define ptr @"kfun:kotlin#<Short-box>(kotlin.Short){}kotlin.Any"(i16 signext %0, ptr %1) #0 !dbg !18 {
entry:
  ret ptr %1, !dbg !19
}

define double @"kfun:kotlin.native.internal.HexStringParser.Companion#parseDouble(kotlin.String){}kotlin.Double"(ptr %0, ptr %1) #0 !dbg !12 {
entry:
  %r = call double @"kfun:demo#regexParse(kotlin.String){}kotlin.Double"(ptr %1), !dbg !13
  ret double %r, !dbg !13
}

define internal void @"kfun:kotlin.text.$init_global$_CharCategories.kt#internal"() #0 !dbg !14 {
entry:
  %0 = alloca ptr, align 4
  %1 = call ptr @"kfun:kotlin.collections#copyOf__at__kotlin.IntArray(){}kotlin.IntArray"(ptr @1, ptr %0), !dbg !15
  store ptr %1, ptr @"kvar:kotlin.text.rangeStart#internal", align 4, !dbg !15
  ret void, !dbg !15
}

define internal void @"kfun:kotlin.random.NativeRandom.<init>#internal"(ptr %this) #0 !dbg !16 {
entry:
  %seed = call i64 @Kotlin_system_getSteadyTimeNanos(), !dbg !17
  store i64 %seed, ptr %this, align 8, !dbg !17
  ret void, !dbg !17
}

declare ptr @"kfun:kotlin.collections#copyOf__at__kotlin.IntArray(){}kotlin.IntArray"(ptr, ptr) #0
declare double @"kfun:demo#regexParse(kotlin.String){}kotlin.Double"(ptr) #0
declare i64 @Kotlin_system_getSteadyTimeNanos() #0

attributes #0 = { "target-cpu"="arm1176jzf-s" "target-features"="+armv6kz,+dsp,+vfp2" }

!llvm.dbg.cu = !{!0}
!llvm.module.flags = !{!2, !3}
!0 = distinct !DICompileUnit(language: DW_LANG_C89, file: !1, producer: "kotlin-compiler: 2.4.21", isOptimized: false, runtimeVersion: 2, emissionKind: FullDebug)
!1 = !DIFile(filename: "demo.kt", directory: "/src")
!2 = !{i32 2, !"Debug Info Version", i32 3}
!3 = !{i32 2, !"Dwarf Version", i32 4}
!4 = !DISubroutineType(types: !5)
!5 = !{}
!10 = distinct !DISubprogram(name: "bridge", scope: !1, file: !1, line: 1, type: !4, scopeLine: 1, spFlags: DISPFlagDefinition, unit: !0)
!11 = !DILocation(line: 1, column: 1, scope: !10)
!12 = distinct !DISubprogram(name: "parseDouble", scope: !1, file: !1, line: 2, type: !4, scopeLine: 2, spFlags: DISPFlagDefinition, unit: !0)
!13 = !DILocation(line: 2, column: 1, scope: !12)
!14 = distinct !DISubprogram(name: "tables", scope: !1, file: !1, line: 3, type: !4, scopeLine: 3, spFlags: DISPFlagDefinition, unit: !0)
!15 = !DILocation(line: 3, column: 1, scope: !14)
!16 = distinct !DISubprogram(name: "NativeRandom", scope: !1, file: !1, line: 4, type: !4, scopeLine: 4, spFlags: DISPFlagDefinition, unit: !0)
!17 = !DILocation(line: 4, column: 1, scope: !16)
!18 = distinct !DISubprogram(name: "box", scope: !1, file: !1, line: 5, type: !4, spFlags: DISPFlagDefinition, unit: !0)
!19 = !DILocation(line: 5, column: 1, scope: !18)
'''


# The first use of a class's globals as Kotlin/Native 2.5 writes it: the class is the last argument of both calls
# (null for a file's globals). Kotlin/Native 2.4 writes the same without that argument.
INIT_MODULE = r'''target datalayout = "e-m:e-p:32:32-Fi8-i64:64-v128:64:128-a:0:32-n32-S64"
target triple = "armv6kz-unknown-linux-gnueabihf"

@"kclass:app.Box" = external global ptr
@"state_global$app.Box" = internal global i32 0, align 4
@"state_thread_local$app.Box" = internal thread_local global i32 0, align 4
@text = internal unnamed_addr constant [33 x i8] c"call @CallInitGlobalPossiblyLock("

define void @"kfun:app#use(){}"() #0 personality ptr @__gxx_personality_v0 {
entry:
  call void @CallInitGlobalPossiblyLock(ptr noundef @"state_global$app.Box", ptr noundef @"kfun:app.Box.$init_global#internal", ptr noundef @"kclass:app.Box")
  invoke void @CallInitGlobalPossiblyLock(ptr noundef @"state_global$app.Box", ptr noundef @"kfun:app.Box.$init_global#internal", ptr noundef null)
          to label %next unwind label %cleanup

next:
  call void @CallInitThreadLocal(ptr noundef @"state_global$app.Box", ptr noundef @"state_thread_local$app.Box", ptr noundef @"kfun:app.Box.$init_thread_local#internal", ptr noundef @"kclass:app.Box")
  ret void

cleanup:
  %0 = landingpad { ptr, i32 }
          cleanup
  resume { ptr, i32 } %0
}

declare void @"kfun:app.Box.$init_global#internal"() #0
declare void @"kfun:app.Box.$init_thread_local#internal"() #0
declare void @CallInitGlobalPossiblyLock(ptr noundef, ptr noundef, ptr noundef) #1
declare void @CallInitThreadLocal(ptr noundef, ptr noundef, ptr noundef, ptr noundef) #1
declare i32 @__gxx_personality_v0(...)

attributes #0 = { "target-cpu"="arm1176jzf-s" "target-features"="+armv6kz,+dsp,+vfp2" }
attributes #1 = { nounwind }
'''

# Two table files as the compiler writes them. The initialiser of the first only points its globals at the tables;
# that of the second also calls a function.
TABLE_MODULE = r"""target datalayout = "e-m:e-p:32:32-Fi8-i64:64-v128:64:128-a:0:32-n32-S64"
target triple = "armv6kz-unknown-linux-gnueabihf"

@1 = internal unnamed_addr constant [4 x i32] [i32 1, i32 2, i32 3, i32 4]
@2 = internal unnamed_addr constant [2 x i32] [i32 5, i32 6]
@"kvar:kotlin.text.rangeStart#internal.2" = internal global ptr null, align 4
@"kvar:kotlin.text.rangeLength#internal" = internal global ptr null, align 4
@"kvar:kotlin.text.keys#internal" = internal global ptr null, align 4
@"state_global$kotlin.text$_LetterChars.kt" = internal global i32 0
@"state_global$kotlin.text$_OtherChars.kt" = internal global i32 0

define internal void @"kfun:kotlin.text.$init_global$_LetterChars.kt#internal"() #0 {
prologue:
  %0 = alloca ptr, i32 5, align 4
  br label %locals_init

locals_init:                                      ; preds = %prologue
  %1 = phi ptr [ %0, %prologue ]
  %2 = getelementptr ptr, ptr %1, i32 3
  %3 = getelementptr ptr, ptr %1, i32 4
  call void @EnterFrame(ptr noundef %1, i32 noundef 0, i32 noundef 5) #1
  br label %entry

entry:                                            ; preds = %locals_init
  %4 = call ptr @"kfun:kotlin.collections#copyOf__at__kotlin.IntArray(){}kotlin.IntArray"(ptr @1, ptr %2)
  br label %returnable_block_exit

returnable_block_exit:                            ; preds = %entry
  %5 = phi ptr [ %4, %entry ]
  call void @RegisterGlobal(ptr noundef @"kvar:kotlin.text.rangeStart#internal.2") #1
  call void @UpdateHeapRef(ptr noundef @"kvar:kotlin.text.rangeStart#internal.2", ptr noundef %5) #1
  %6 = call ptr @"kfun:kotlin.collections#copyOf__at__kotlin.IntArray(){}kotlin.IntArray"(ptr @2, ptr %3)
  br label %returnable_block_exit1

returnable_block_exit1:                           ; preds = %returnable_block_exit
  %7 = phi ptr [ %6, %returnable_block_exit ]
  call void @RegisterGlobal(ptr noundef @"kvar:kotlin.text.rangeLength#internal") #1
  call void @UpdateHeapRef(ptr noundef @"kvar:kotlin.text.rangeLength#internal", ptr noundef %7) #1
  call void @LeaveFrame(ptr noundef %1, i32 noundef 0, i32 noundef 5) #1
  ret void
}

define internal void @"kfun:kotlin.text.$init_global$_OtherChars.kt#internal"() #0 {
entry:
  %0 = alloca ptr, align 4
  %1 = call ptr @"kfun:kotlin.collections#copyOf__at__kotlin.IntArray(){}kotlin.IntArray"(ptr @1, ptr %0)
  call void @RegisterGlobal(ptr noundef @"kvar:kotlin.text.keys#internal") #1
  call void @UpdateHeapRef(ptr noundef @"kvar:kotlin.text.keys#internal", ptr noundef %1) #1
  call void @"kfun:kotlin.text#fill(){}"()
  ret void
}

define i32 @"kfun:kotlin.text#isLetterImpl__at__kotlin.Char(){}kotlin.Boolean"(i32 %0) #0 {
entry:
  %1 = load i32, ptr @"state_global$kotlin.text$_LetterChars.kt", align 4
  %2 = icmp eq i32 %1, 2
  br i1 %2, label %ready, label %first

first:
  call void @CallInitGlobalPossiblyLock(ptr noundef @"state_global$kotlin.text$_LetterChars.kt", ptr noundef @"kfun:kotlin.text.$init_global$_LetterChars.kt#internal")
  call void @CallInitGlobalPossiblyLock(ptr noundef @"state_global$kotlin.text$_OtherChars.kt", ptr noundef @"kfun:kotlin.text.$init_global$_OtherChars.kt#internal")
  br label %ready

ready:
  %3 = load ptr, ptr @"kvar:kotlin.text.rangeStart#internal.2", align 4
  %4 = load i32, ptr %3, align 4
  ret i32 %4
}

declare ptr @"kfun:kotlin.collections#copyOf__at__kotlin.IntArray(){}kotlin.IntArray"(ptr, ptr) #0
declare void @"kfun:kotlin.text#fill(){}"() #0
declare void @EnterFrame(ptr, i32, i32)
declare void @LeaveFrame(ptr, i32, i32)
declare void @RegisterGlobal(ptr)
declare void @UpdateHeapRef(ptr, ptr)
declare void @CallInitGlobalPossiblyLock(ptr, ptr)

attributes #0 = { "target-cpu"="arm1176jzf-s" "target-features"="+armv6kz,+dsp,+vfp2" }
attributes #1 = { nounwind }
"""


def body(text, name):
    m = re.search(r'^define [^\n]*@"' + re.escape(name) + r'"[^\n]*\{$(.*?)^\}$', text, re.M | re.S)
    return m.group(1) if m else None


@unittest.skipUnless(HAVE_CLANG, 'needs the LLVM of Kotlin/Native (python toolchain/paths.py)')
class RetargetTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        OUT.mkdir(parents=True, exist_ok=True)
        (OUT / 'in.ll').write_text(MODULE, encoding='utf-8')
        (OUT / 'debug.ll').write_text(DEBUG_MODULE, encoding='utf-8')

    def retarget(self, *opts, name='out.ll', src='in.ll'):
        r = subprocess.run([sys.executable, ROOT / 'toolchain/retarget.py', OUT / src, OUT / name, *opts],
                           capture_output=True, text=True)
        text = (OUT / name).read_text(encoding='utf-8') if r.returncode == 0 else ''
        return r, text

    def test_debug_info_stays_valid(self):
        r, text = self.retarget('--no-tls', '--single-core', '--size', '--hot', 'NativeRandom', src='debug.ll',
                                name='debug_out.ll')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn('define void @bridge() #9999 !dbg !10 {', text)
        self.assertIn('%1 = getelementptr inbounds i8, ptr @1, i32 0, !dbg !15', text)
        self.assertIn('%seed = call i64 @kmicro_random_seed(), !dbg !17', text)
        self.assertRegex(text, r'define double @"[^"]*parseDouble[^"]*"\(ptr %0, ptr %1\) #\d+ \{')
        self.assertRegex(text, r'define ptr @"kfun:kotlin#<Short-box>[^"]*"\([^\n]*\) noinline #\d+ !dbg !18 \{')
        c = subprocess.run([str(paths.clang()), *paths.target_flags(), '-O2', '-c', '-x', 'ir', OUT / 'debug_out.ll',
                            '-o', OUT / 'debug_out.o'], capture_output=True, text=True)
        self.assertEqual(c.returncode, 0, c.stderr)
        self.assertNotIn('invalid debug info', c.stderr)

    def test_attributes_equal_clang(self):
        c = subprocess.run([str(paths.clang()), *paths.target_flags(), '-S', '-emit-llvm', '-x', 'c', '-', '-o', '-'],
                           input='int g(int x) { return x + 1; }\n', capture_output=True, text=True)
        want = {re.search(r'"target-cpu"="[^"]*"', c.stdout).group(0),
                re.search(r'"target-features"="[^"]*"', c.stdout).group(0)}
        r, text = self.retarget()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(set(re.findall(r'"target-(?:cpu|features)"="[^"]*"', text)), want)
        self.assertRegex(text, r'define void @bridge\(\) #9999 \{')       # a definition without attributes gets them
        self.assertIn('target triple = "thumbv7em-unknown-none-eabihf"', text)

    def test_no_tls_and_single_core(self):
        r, text = self.retarget()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn('@"state_thread_local$demo" = internal thread_local global', text)
        self.assertIn('load atomic i32, ptr @"state_global$demo" acquire, align 4', text)
        r, text = self.retarget('--no-tls', '--single-core')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn(' thread_local ', text)
        self.assertIn('@"state_thread_local$demo" = internal global i32 0, align 4', text)
        self.assertIn('%0 = load i32, ptr @"state_global$demo", align 4', body(text, 'kfun:state#touch(){}'))
        self.assertIn('single-core: 1 init-state loads made plain', r.stderr)

    def test_init_calls_with_the_class(self):
        (OUT / 'init25.ll').write_text(INIT_MODULE, encoding='utf-8')
        r, text = self.retarget(src='init25.ll')
        self.assertEqual(r.returncode, 0, r.stderr)
        use = body(text, 'kfun:app#use(){}')
        self.assertEqual(re.findall(r'^  (?:call|invoke) void @(\w+)\(', use, re.M),
                         ['kmicro_init_global', 'kmicro_init_global', 'kmicro_init_thread_local'])
        self.assertIn(', ptr noundef @"kfun:app.Box.$init_global#internal", ptr noundef @"kclass:app.Box")\n', use)
        self.assertIn('declare void @kmicro_init_global(ptr noundef, ptr noundef, ptr noundef) #1\n', text)
        self.assertIn('declare void @kmicro_init_thread_local(ptr noundef, ptr noundef, ptr noundef, ptr noundef) #1\n',
                      text)
        self.assertEqual(text.count('@CallInit'), 1)
        self.assertIn('c"call @CallInitGlobalPossiblyLock("\n', text)               # the string literal is as it was
        c = subprocess.run([str(paths.clang()), *paths.target_flags(), '-O2', '-c', '-x', 'ir', OUT / 'out.ll',
                            '-o', OUT / 'out.o'], capture_output=True, text=True)
        self.assertEqual(c.returncode, 0, c.stderr)

    def test_init_calls_without_the_class_keep_their_names(self):
        module = INIT_MODULE                                                         # as Kotlin/Native 2.4 writes it
        for old, new in ((', ptr noundef @"kclass:app.Box")', ')'), (', ptr noundef null)', ')'),
                         ('Lock(ptr noundef, ptr noundef, ptr noundef) #1', 'Lock(ptr noundef, ptr noundef) #1'),
                         ('Local(ptr noundef, ptr noundef, ptr noundef, ptr noundef) #1',
                          'Local(ptr noundef, ptr noundef, ptr noundef) #1')):
            self.assertIn(old, module)
            module = module.replace(old, new)
        (OUT / 'init24.ll').write_text(module, encoding='utf-8')
        r, text = self.retarget(src='init24.ll')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn('kmicro_init_', text)
        self.assertEqual(re.findall(r'^  (?:call|invoke) void @(\w+)\(', body(text, 'kfun:app#use(){}'), re.M),
                         ['CallInitGlobalPossiblyLock', 'CallInitGlobalPossiblyLock', 'CallInitThreadLocal'])
        self.assertIn('declare void @CallInitThreadLocal(ptr noundef, ptr noundef, ptr noundef) #1\n', text)

    def test_string_constants_are_not_edited(self):
        # -Xbinary=latin1Strings=true stores a literal as its text, which may be the text a rewrite looks for
        strings = ('a thread_local value', '@tls = internal thread_local(initialexec) global i32 0, align 4',
                   'load atomic i32, ptr @"state_global$demo" acquire, align 4', 'attributes #1 = { }',
                   '"target-cpu"="arm1176jzf-s" "target-features"="+vfp2"', 'define void @bridge() {',
                   'call i64 @Kotlin_system_getSteadyTimeNanos()', '@llvm.global_ctors = ')
        consts = ['@str%d = internal unnamed_addr constant [%d x i8] c"%s"' % (i, len(s), s.replace('"', r'\22'))
                  for i, s in enumerate(strings)]
        tls = '@"kvar:demo.thread_local x" = internal thread_local(initialexec) global i32 0, align 4'
        (OUT / 'strings.ll').write_text('\n'.join([MODULE, *consts, tls, '']), encoding='utf-8')
        r, text = self.retarget('--no-tls', '--single-core', '--size', '--drop-ctors', src='strings.ll')
        self.assertEqual(r.returncode, 0, r.stderr)
        for const in consts:
            self.assertIn(const + '\n', text)
        self.assertIn('@"kvar:demo.thread_local x" = internal global i32 0, align 4\n', text)
        self.assertIn('@"state_thread_local$demo" = internal global i32 0, align 4\n', text)
        c = subprocess.run([str(paths.clang()), *paths.target_flags(), '-O2', '-c', '-x', 'ir', OUT / 'out.ll',
                            '-o', OUT / 'out.o'], capture_output=True, text=True)
        self.assertEqual(c.returncode, 0, c.stderr)

    def test_cut_off_attribute_cache_is_rebuilt(self):
        self.retarget()
        cache = OUT / 'target_attributes.txt'
        full = cache.read_text(encoding='utf-8')
        cache.write_text(full[:-40], encoding='utf-8')                   # a write stopped part-way
        r, text = self.retarget()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(cache.read_text(encoding='utf-8'), full)
        self.assertIn(full.splitlines()[2], text)

    def test_output_compiles(self):
        for opts in ((), ('--no-tls', '--single-core', '--size', '--hot', 'fast')):
            r, _ = self.retarget(*opts)
            self.assertEqual(r.returncode, 0, r.stderr)
            c = subprocess.run([str(paths.clang()), *paths.target_flags(), '-O2', '-c', '-x', 'ir', OUT / 'out.ll',
                                '-o', OUT / 'out.o'], capture_output=True, text=True)
            self.assertEqual(c.returncode, 0, c.stderr)

    def test_the_integer_box_functions_are_never_inlined(self):
        # tools/isr_check.py --boxing finds a box by the call to one of them
        for opts in ((), ('--no-tls', '--single-core', '--size', '--hot', 'kotlin')):
            r, text = self.retarget(*opts)
            self.assertEqual(r.returncode, 0, r.stderr)
            kept = re.findall(r'^define [^\n]*@"kfun:[^"]*#<(\w+)-box>[^\n]* noinline #\d+ ', text, re.M)
            self.assertEqual(kept, ['Int', 'ULong'], opts)
            self.assertNotIn('noinline', body(text, 'kfun:app#boxed(kotlin.Int){}kotlin.Any'))

    def test_hot(self):
        for regex, hot in (('^kfun:demo#', 4), ('^kfun:demo#fast', 1), (r'kotlin\.Int$', 1), ('§', 1)):
            r, text = self.retarget('--size', '--hot', regex)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn(f'size: minsize everywhere except {hot} hot functions', r.stderr)
        self.assertRegex(text, r'define ptr @"kfun:demo#first\(\)[^\n]*#90000 \{')
        self.assertNotIn('minsize', re.search(r'^attributes #90000 = .*$', text, re.M).group(0))

    def test_size_keeps_the_outliner_away(self):
        r, text = self.retarget('--size')
        self.assertEqual(r.returncode, 0, r.stderr)
        groups = re.findall(r'^attributes #\d+ = .*$', text, re.M)
        self.assertTrue(groups)
        for g in groups:                        # an outlined call sequence gets a wrong unwind entry on Thumb-2
            self.assertEqual('minsize' in g, '"nooutline"' in g, g)
        self.assertTrue(any('minsize' in g for g in groups))
        self.assertNotIn('"nooutline"', self.retarget()[1])

    def test_hot_errors(self):
        for opts, message in ((('--size', '--hot', '^nothing'), 'matches no function'),
                              (('--size', '--hot', '(unclosed'), 'is not a valid regular expression'),
                              (('--hot', 'fast'), 'only applies with --size')):
            r, _ = self.retarget(*opts)
            self.assertNotEqual(r.returncode, 0)
            self.assertIn(message, r.stderr)
            self.assertNotIn('Traceback', r.stderr)

    def test_input_that_is_not_ir(self):
        (OUT / 'notes.ll').write_text('this is not LLVM IR\n', encoding='utf-8')
        (OUT / 'empty.ll').write_text('', encoding='utf-8')
        (OUT / 'bitcode.ll').write_bytes(b'BC\xc0\xde\x35\x14\x00\x00')
        for src in ('notes.ll', 'empty.ll', 'bitcode.ll'):
            r, _ = self.retarget('--no-tls', src=src)
            self.assertEqual(r.returncode, 1, src)
            self.assertEqual(r.stderr, f'retarget: {OUT / src} is not textual LLVM IR (no target datalayout)\n')

    def test_random_seed_from_hook(self):
        _, text = self.retarget()
        self.assertIn('call i64 @kmicro_random_seed()', body(text, 'kfun:kotlin.random.NativeRandom.<init>#internal'))
        self.assertIn('call i64 @Kotlin_system_getSteadyTimeNanos()', body(text, 'kfun:demo#now(){}kotlin.Long'))
        self.assertIn('declare i64 @kmicro_random_seed()', text)

    def test_hex_parser_calls_runtime(self):
        _, text = self.retarget()
        hex_parser = 'kfun:kotlin.native.internal.HexStringParser.Companion'
        self.assertEqual(body(text, hex_parser + '.<init>#internal').strip(), 'ret void')
        self.assertIn('@kmicro_hex_to_double(ptr %1)',
                      body(text, hex_parser + '#parseDouble(kotlin.String){}kotlin.Double'))
        self.assertIn('@kmicro_hex_to_float(ptr %1)', body(text, hex_parser + '#parseFloat(kotlin.String){}kotlin.Float'))
        self.assertNotIn('regexParse', body(text, hex_parser + '#parseFloat(kotlin.String){}kotlin.Float'))

    def test_unicode_tables_stay_constant(self):
        _, text = self.retarget()
        table = body(text, 'kfun:kotlin.text.$init_global$_CharCategories.kt#internal')
        self.assertIn('%1 = getelementptr inbounds i8, ptr @1, i32 0', table)
        self.assertNotIn('copyOf', table)
        self.assertIn('copyOf', body(text, 'kfun:demo#copy(){}'))         # user code keeps its copy

    def test_a_table_file_with_nothing_else_to_do_starts_as_initialised(self):
        # no first use is left, so an interrupt handler may be the first to read the tables
        (OUT / 'tables.ll').write_text(TABLE_MODULE, encoding='utf-8')
        r, text = self.retarget(src='tables.ll')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn('retarget: warning', r.stderr)
        self.assertIn('@"kvar:kotlin.text.rangeStart#internal.2" = internal global ptr @1, align 4\n', text)
        self.assertIn('@"kvar:kotlin.text.rangeLength#internal" = internal global ptr @2, align 4\n', text)
        self.assertIn('@"state_global$kotlin.text$_LetterChars.kt" = internal global i32 2\n',
                      text)
        # an initialiser that does more stays one: its tables are constants, its file has a first use
        self.assertIn('@"kvar:kotlin.text.keys#internal" = internal global ptr null, align 4\n', text)
        self.assertIn('@"state_global$kotlin.text$_OtherChars.kt" = internal global i32 0\n',
                      text)
        self.assertNotIn('copyOf', body(text, 'kfun:kotlin.text.$init_global$_OtherChars.kt#internal'))
        c = subprocess.run([str(paths.clang()), *paths.target_flags(), '-O2', '-c', '-x', 'ir', OUT / 'out.ll', '-o',
                            OUT / 'tables.o'], capture_output=True, text=True)
        self.assertEqual(c.returncode, 0, c.stderr)

    def warnings(self, module, src):
        (OUT / src).write_text(module, encoding='utf-8')
        r, _ = self.retarget(src=src)
        self.assertEqual(r.returncode, 0, r.stderr)
        return [line for line in r.stderr.splitlines() if line.startswith('retarget: warning: ')]

    def test_rewrites_that_match_do_not_warn(self):
        self.assertEqual(self.warnings(MODULE, 'in.ll'), [])
        self.assertEqual(self.warnings(DEBUG_MODULE, 'debug.ll'), [])

    def test_module_without_the_stdlib_code_does_not_warn(self):
        user_code = re.sub(r'^define [^\n]*@"kfun:kotlin\.[^\n]*\{$.*?^\}$\n', '', MODULE, flags=re.M | re.S)
        self.assertNotIn('NativeRandom', user_code)
        self.assertIn('kfun:demo#now', user_code)
        self.assertEqual(self.warnings(user_code, 'user.ll'), [])

    def test_rewrite_that_matches_nothing_warns(self):
        # the code each rewrite looks for, written as another compiler version might write it
        hex_parser = 'kfun:kotlin.native.internal.HexStringParser.Companion'
        for name, old, new, symbol, effect in (
                ('clock', '%seed = call i64 @Kotlin_system_getSteadyTimeNanos()', '%seed = call i64 @other_clock()',
                 'kfun:kotlin.random.NativeRandom.<init>#internal', 'seed from the clock'),
                ('init', 'Companion.<init>#internal"(ptr %0)', 'Companion.<init>#internal"(ptr %0, ptr %1)',
                 hex_parser + '.<init>#internal', 'Regex engine'),
                ('double', '{}kotlin.Double"(ptr %0, ptr %1)', '{}kotlin.Double"(ptr %0, ptr %1, ptr %2)',
                 hex_parser + '#parseDouble(kotlin.String){}kotlin.Double', 'Regex engine'),
                ('float', 'Companion#parseFloat(kotlin.String)', 'Companion#parseFloat(kotlin.CharSequence)',
                 hex_parser + '#parseFloat(kotlin.CharSequence){}kotlin.Float', 'Regex engine'),
                ('tables', 'collections#copyOf__at__', 'collections#copyOfRange__at__',
                 'kfun:kotlin.text.$init_global$_CharCategories.kt#internal', 'Unicode tables')):
            self.assertIn(old, MODULE, name)
            lines = self.warnings(MODULE.replace(old, new), f'changed_{name}.ll')
            self.assertEqual(len(lines), 1, (name, lines))
            self.assertIn(f'although the module defines {symbol}: ', lines[0])
            self.assertIn(effect, lines[0])
            self.assertIn(f'Kotlin/Native {paths.KOTLIN_NATIVE_VERSION}', lines[0])


if __name__ == '__main__':
    unittest.main()
