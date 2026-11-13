#include "kmicro.h"
void k_start(void) __asm__("kfun:#start(){}");
int32_t k_event(int32_t kind, int32_t arg) __asm__("kfun:#event(kotlin.Int;kotlin.Int){}kotlin.Int");
int main(void)
{
    kmicro_init();
    k_start();
    /* Device.on(): Press -> 1 undocked / 2 docked (+log), Dock -> 3 (+log, toggles), Tick(ms) -> 4 if ms > 1000 else 0 */
    static const int32_t ev[][3] = {          /* kind, arg, expected return = last*1000 + log.size */
        { 0, 0, 1001 }, { 1, 0, 3002 }, { 0, 0, 2003 }, { 2, 500, 3 }, { 2, 1500, 4003 }, { 1, 0, 3004 }, { 0, 0, 1005 },
    };
    int bad = 0;
    for (unsigned i = 0; i < sizeof ev / sizeof ev[0]; i++) {
        int32_t r = k_event(ev[i][0], ev[i][1]);
        if (r != ev[i][2]) {
            bad++;
            kmicro_puts("  step "); kmicro_put_int((int32_t)i); kmicro_puts(" got "); kmicro_put_int(r);
            kmicro_puts(" expected "); kmicro_put_int(ev[i][2]); kmicro_puts("\n");
        }
    }
    for (int i = 0; i < 400; i++)              /* long run: the log grows to 400+ strings -> GC must keep them */
        k_event(i & 1, 0);
    int32_t r = k_event(2, 0);                 /* Tick(0) -> 0, log size */
    kmicro_stats_t st;
    kmicro_stats(&st);
    kmicro_puts("app: last*1000+log = "); kmicro_put_int(r);
    kmicro_puts("  gcs="); kmicro_put_int((int32_t)st.gc_count);
    kmicro_puts(" peak="); kmicro_put_int((int32_t)st.peak_bytes);
    kmicro_puts(bad == 0 && r == 405 ? "  OK\n" : "  WRONG\n");
    return bad || r != 405;
}
