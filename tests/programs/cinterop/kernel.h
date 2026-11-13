#include <stdint.h>
/* The C kernel API that Kotlin may call (prototype for the cinterop experiment). */
int32_t k_button_count(void);
void k_sound_play(int32_t clip, int32_t volume);
uint32_t k_now_ms(void);
void k_log_text(const char *utf8);
