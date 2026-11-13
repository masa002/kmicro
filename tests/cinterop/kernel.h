#include <stdint.h>
/* A C API that Kotlin calls through cinterop (kernel.def); main.c implements it. */
int32_t k_button_count(void);
void k_sound_play(int32_t clip, int32_t volume);
uint32_t k_now_ms(void);
void k_log_text(const char *utf8);
