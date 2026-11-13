#include "kmicro.h"
void kt_main(void) __asm__("kfun:#main(){}");
int main(void)
{
    kmicro_init();
    kt_main();
    return 0;
}
