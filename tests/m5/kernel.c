/* A fake C kernel for the cinterop test: the functions Kotlin calls through kmicro.example.kernel. */
#include "kmicro.h"
static int32_t s_sound_clip = -1, s_sound_vol = -1, s_logs;
int32_t k_button_count(void) { return 3; }
void k_sound_play(int32_t clip, int32_t volume) { s_sound_clip = clip; s_sound_vol = volume; }
uint32_t k_now_ms(void) { return 1000; }
void k_log_text(const char *utf8) { kmicro_puts("[kernel log] "); kmicro_puts(utf8); kmicro_puts("\n"); s_logs++; }

int32_t k_poke(int32_t n) __asm__("kfun:#poke(kotlin.Int){}kotlin.Int");
int main(void)
{
    kmicro_init();
    int32_t r = k_poke(7);
    bool ok = r == 1003 && s_sound_clip == 7 && s_sound_vol == 80 && s_logs == 1;
    kmicro_puts("cinterop: poke(7) = "); kmicro_put_int(r);
    kmicro_puts(ok ? "  OK\n" : "  WRONG\n");
    return ok ? 0 : 1;
}
