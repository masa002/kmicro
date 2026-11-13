// Floating-point code in main: LTO inlines main into the C start code, so the FPU must be on before that code runs.
fun main() {
    println("toDouble + 1: " + ("1.5".toDouble() + 1))
    println("Duration.parse: " + kotlin.time.Duration.parse("1.5s"))
}
