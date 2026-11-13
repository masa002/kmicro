// Known not to work on kmicro yet: kotlin.system.exitProcess stops with "unimplemented runtime symbol:
// Kotlin_system_exitProcess" instead of ending the program with its status.
// Not run by default: python tools/difftest.py d_known_exit_process
fun main() {
    println("before exitProcess")
    kotlin.system.exitProcess(0)
}
