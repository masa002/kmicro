// Does not work on kmicro: a public function whose backtick name contains spaces. kotlinc-native compiles it,
// but the C export it writes for a static library (-p static, which kmicro builds) cannot name it, so the kmicro build
// fails. A private or internal function with such a name works (d_lang_11.kt).
// Not run by default: python tools/difftest.py d_known_backtick_name
fun `public name with spaces`() = "backticks ok"

fun main() {
    println(`public name with spaces`())
    println("done")
}
