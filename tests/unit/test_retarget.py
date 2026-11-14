"""toolchain/retarget.py on a small IR module shaped like kotlinc-native's output: the target attributes equal clang's
for paths.target_flags(), --no-tls, --single-core, --hot, and the stdlib rewrites (Random seed, hex float parser, Unicode
tables). The output must compile with clang.

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
'''


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

    def test_hot(self):
        for regex, hot in (('^kfun:demo#', 4), ('^kfun:demo#fast', 1), (r'kotlin\.Int$', 1), ('§', 1)):
            r, text = self.retarget('--size', '--hot', regex)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn(f'size: minsize everywhere except {hot} hot functions', r.stderr)
        self.assertRegex(text, r'define ptr @"kfun:demo#first\(\)[^\n]*#90000 \{')
        self.assertNotIn('minsize', re.search(r'^attributes #90000 = .*$', text, re.M).group(0))

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


if __name__ == '__main__':
    unittest.main()
