/* A symbol nothing defines: qbuild's link must fail and name the file that needs it (it stubs only runtime natives
 * that Kotlin code calls). */
#include "kmicro.h"

extern int32_t sensor_offset;

int main(void)
{
    kmicro_init();
    return sensor_offset;
}
