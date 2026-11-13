/* A tiny image for test_symbolize.py: top() ends with a call that never returns (sink), reached through two inlined
 * functions, so its return address is already the first instruction of the next function. */
__attribute__((noinline, noreturn)) void sink(int x) { __asm volatile("" :: "r"(x)); for (;;) {} }
__attribute__((noinline)) void plain(int x) { __asm volatile("" :: "r"(x)); }
static inline void level3(int x) { sink(x + 3); }
static inline void level2(int x) { if (x > 5) level3(x * 2); plain(x); }
__attribute__((noinline)) int top(int x) { level2(x); plain(x + 1); return x; }
int main(void) { return top(7); }
void _start(void) { main(); }
