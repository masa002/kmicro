@file:OptIn(kotlinx.cinterop.ExperimentalForeignApi::class, kotlin.experimental.ExperimentalNativeApi::class)
import kmicro.example.kernel.*
import kotlin.native.CName

// Calls C functions through cinterop: an Int and a String argument, Int and UInt results (kernel.h, main.c).
@CName("k_poke")
fun poke(n: Int): Int {
    k_sound_play(n, 80)
    k_log_text("poked $n")
    return k_button_count() + k_now_ms().toInt()
}
