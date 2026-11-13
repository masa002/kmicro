@file:OptIn(kotlinx.cinterop.ExperimentalForeignApi::class)
import kmicro.example.kernel.*

fun poke(n: Int): Int {
    k_sound_play(n, 80)
    k_log_text("poked $n")
    return k_button_count() + k_now_ms().toInt()
}
