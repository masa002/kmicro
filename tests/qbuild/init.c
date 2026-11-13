/* qbuild with several C files and no Kotlin: this driver has the name of a runtime file (runtime/init.c), and
 * support/hw.c, the second file, provides hw_rd32/hw_wr32 through support/ on the include path. */
#include "kmicro.h"
#include "hw.h"

static uint32_t s_word;

int main(void)
{
    kmicro_init();
    hw_wr32((uint32_t)&s_word, 1234u);
    uint32_t got = hw_rd32((uint32_t)&s_word);
    kmicro_puts("word = ");
    kmicro_put_int((int32_t)got);
    kmicro_puts("\n");
    return got == 1234u ? 0 : 1;
}
