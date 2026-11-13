/* The Unicode decomposition natives of kotlin.text.Regex (Regex.cpp of the stock runtime). Only canonical equivalence
 * (RegexOption.CANON_EQ) uses them: Lexer.normalize, Pattern.processDecomposedChar and DecomposedCharSet. kmicro has
 * no decomposition tables, so each one throws IllegalArgumentException, which the caller can catch; every other
 * Regex, and String.toDouble() that links the Regex engine, never calls them. */
#include "kmicro.h"

ObjHeader *CreateStringFromCString(const char *c, ObjHeader **result);
__attribute__((noreturn)) void ThrowIllegalArgumentExceptionWithMessage(ObjHeader *message);   /* RuntimeUtils.kt */
void EnterFrame(ObjHeader **start, int parameters, int count);

__attribute__((noreturn)) static void canon_eq(void)
{
    /* A callee does not root its parameters: the message stays in this frame's slot while the exception is made.
     * The catcher's SetCurrentFrame pops the frame. */
    struct { FrameOverlay f; ObjHeader *message; } fr = { { 0, 0, 0 }, 0 };
    EnterFrame((ObjHeader **)&fr, 0, sizeof fr / sizeof(ObjHeader *));
    CreateStringFromCString("RegexOption.CANON_EQ is not supported on kmicro", &fr.message);
    ThrowIllegalArgumentExceptionWithMessage(fr.message);
}

int32_t Kotlin_text_regex_getCanonicalClassInternal(int32_t ch) { (void)ch; canon_eq(); }
bool Kotlin_text_regex_hasSingleCodepointDecompositionInternal(int32_t ch) { (void)ch; canon_eq(); }
ObjHeader *Kotlin_text_regex_getDecompositionInternal(int32_t ch, ObjHeader **result)
{
    (void)ch;
    (void)result;
    canon_eq();
}
int32_t Kotlin_text_regex_decomposeString(ObjHeader *input, int32_t length, ObjHeader *output)
{
    (void)input;
    (void)length;
    (void)output;
    canon_eq();
}
int32_t Kotlin_text_regex_decomposeCodePoint(int32_t code_point, ObjHeader *output, int32_t from)
{
    (void)code_point;
    (void)output;
    (void)from;
    canon_eq();
}
