"""toolchain/retarget.py on a small IR module shaped like kotlinc-native's output: the target attributes equal clang's
for paths.TARGET_M4F, --hot, and the stdlib rewrites (Random seed, hex float parser, Unicode tables). The output must
compile with clang.

usage: python -m unittest discover tests/unit       (skipped when Kotlin/Native's LLVM is not installed)
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


def body(text, name):
    m = re.search(r'^define [^\n]*@"' + re.escape(name) + r'"[^\n]*\{$(.*?)^\}$', text, re.M | re.S)
    return m.group(1) if m else None


@unittest.skipUnless(HAVE_CLANG, "needs Kotlin/Native's LLVM (python toolchain/paths.py)")
class RetargetTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        OUT.mkdir(parents=True, exist_ok=True)
        (OUT / 'in.ll').write_text(MODULE, encoding='utf-8')

    def retarget(self, *opts, name='out.ll'):
        r = subprocess.run([sys.executable, ROOT / 'toolchain/retarget.py', OUT / 'in.ll', OUT / name, *opts],
                           capture_output=True, text=True)
        text = (OUT / name).read_text(encoding='utf-8') if r.returncode == 0 else ''
        return r, text

    def test_attributes_equal_clang(self):
        c = subprocess.run([str(paths.clang()), *paths.TARGET_M4F, '-S', '-emit-llvm', '-x', 'c', '-', '-o', '-'],
                           input='int g(int x) { return x + 1; }\n', capture_output=True, text=True)
        want = {re.search(r'"target-cpu"="[^"]*"', c.stdout).group(0),
                re.search(r'"target-features"="[^"]*"', c.stdout).group(0)}
        r, text = self.retarget()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(set(re.findall(r'"target-(?:cpu|features)"="[^"]*"', text)), want)
        self.assertRegex(text, r'define void @bridge\(\) #9999 \{')       # a definition without attributes gets them
        self.assertIn('target triple = "thumbv7em-unknown-none-eabihf"', text)

    def test_output_compiles(self):
        for opts in ((), ('--no-tls', '--single-core', '--size', '--hot', 'fast')):
            r, _ = self.retarget(*opts)
            self.assertEqual(r.returncode, 0, r.stderr)
            c = subprocess.run([str(paths.clang()), *paths.TARGET_M4F, '-O2', '-c', '-x', 'ir', OUT / 'out.ll',
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
