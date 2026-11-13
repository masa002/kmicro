/* Type checks, identity hash, box caches, primitive and object arrays (Types.cpp, Natives.cpp, Boxing.cpp,
 * Arrays.cpp of the stock runtime). */
#include <string.h>
#include "kmicro.h"

/* ---- types ---- */

KM_NOTHROW bool IsSubtype(const TypeInfo *obj_type, const TypeInfo *type)
{
    if (type->flags_ & KM_TF_INTERFACE) {
        for (int32_t i = 0; i < obj_type->implementedInterfacesCount_; i++)
            if (obj_type->implementedInterfaces_[i] == type)
                return true;
        return false;
    }
    while (obj_type != NULL && obj_type != type)
        obj_type = obj_type->superType_;
    return obj_type != NULL;
}
KM_NOTHROW bool IsInstance(const ObjHeader *obj, const TypeInfo *type) { return IsSubtype(km_type_info(obj), type); }
KM_NOTHROW bool IsSubclassFast(const TypeInfo *obj_type, int32_t lo, int32_t hi)
{
    return obj_type->classId_ >= lo && obj_type->classId_ <= hi;
}
KM_NOTHROW bool Kotlin_TypeInfo_isInstance(const ObjHeader *obj, const void *type) { return IsInstance(obj, type); }
KM_NOTHROW const void *Kotlin_Any_getTypeInfo(const ObjHeader *obj) { return km_type_info(obj); }
KM_NOTHROW bool IsArray(const ObjHeader *obj) { return km_type_info(obj)->instanceSize_ < 0; }

/* Non-moving collector: the address is a stable identity hash (Natives.cpp does the same). */
KM_NOTHROW int32_t Kotlin_Any_hashCode(const ObjHeader *obj) { return (int32_t)(uintptr_t)obj; }

ObjHeader *Kotlin_TypeInfo_getPackageName(const void *type, bool check_flags, ObjHeader **result)
{
    const TypeInfo *t = type;
    return km_return(result, (!check_flags || (t->flags_ & KM_TF_REFLECTION_SHOW_PKG_NAME)) ? t->packageName_ : NULL);
}
ObjHeader *Kotlin_TypeInfo_getRelativeName(const void *type, bool check_flags, ObjHeader **result)
{
    const TypeInfo *t = type;
    return km_return(result, (!check_flags || (t->flags_ & KM_TF_REFLECTION_SHOW_REL_NAME)) ? t->relativeName_ : NULL);
}

/* ---- box caches: the compiler emits the permanent box tables and their ranges (Boxing.cpp) ---- */

#define KM_BOX_CACHE(Name, T, NAME)                                                                            \
    extern const T NAME##_RANGE_FROM, NAME##_RANGE_TO;                                                         \
    extern struct { ObjHeader header; T value; } NAME##_CACHE[];                                               \
    KM_NOTHROW bool in##Name##BoxCache(T value) { return value >= NAME##_RANGE_FROM && value <= NAME##_RANGE_TO; } \
    KM_NOTHROW ObjHeader *getCached##Name##Box(T value, ObjHeader **result)                                    \
    {                                                                                                          \
        return km_return(result, &NAME##_CACHE[(int64_t)value - (int64_t)NAME##_RANGE_FROM].header);           \
    }
KM_BOX_CACHE(Boolean, bool, BOOLEAN)
KM_BOX_CACHE(Byte, int8_t, BYTE)
KM_BOX_CACHE(Char, uint16_t, CHAR)
KM_BOX_CACHE(Short, int16_t, SHORT)
KM_BOX_CACHE(Int, int32_t, INT)
KM_BOX_CACHE(Long, int64_t, LONG)

/* ---- arrays (Arrays.cpp): elements start right after the 8-byte header for every element size ---- */

static inline void bounds(const ArrayHeader *a, int32_t index)
{
    if ((uint32_t)index >= a->count_)
        ThrowArrayIndexOutOfBoundsException();
}
static inline void copy_check(const ArrayHeader *src, int32_t from, const ArrayHeader *dst, int32_t to, int32_t n)
{
    if (n < 0 || from < 0 || (uint32_t)n + (uint32_t)from > src->count_ || to < 0 ||
        (uint32_t)n + (uint32_t)to > dst->count_)
        ThrowArrayIndexOutOfBoundsException();
}

/* Element access is a bounds check and one load or store: always inlined into the Kotlin code under LTO (with
 * minsize the inliner would otherwise keep a call per element, several per element in a tight interrupt loop). */
#define KM_ACCESS __attribute__((always_inline))
#define KM_PRIM_ARRAY(Name, T)                                                                                 \
    KM_ACCESS T Kotlin_##Name##Array_get(const ObjHeader *a, int32_t i)                                              \
    {                                                                                                          \
        bounds((const ArrayHeader *)a, i);                                                                     \
        return ((T *)km_array_data((ArrayHeader *)a))[i];                                                      \
    }                                                                                                          \
    KM_ACCESS T Kotlin_##Name##Array_get_without_BoundCheck(const ObjHeader *a, int32_t i)                               \
    {                                                                                                          \
        return ((T *)km_array_data((ArrayHeader *)a))[i];                                                      \
    }                                                                                                          \
    KM_ACCESS void Kotlin_##Name##Array_set(ObjHeader *a, int32_t i, T v)                                            \
    {                                                                                                          \
        bounds((const ArrayHeader *)a, i);                                                                     \
        ((T *)km_array_data((ArrayHeader *)a))[i] = v;                                                         \
    }                                                                                                          \
    KM_ACCESS void Kotlin_##Name##Array_set_without_BoundCheck(ObjHeader *a, int32_t i, T v)                             \
    {                                                                                                          \
        ((T *)km_array_data((ArrayHeader *)a))[i] = v;                                                         \
    }                                                                                                          \
    KM_NOTHROW int32_t Kotlin_##Name##Array_getArrayLength(const ObjHeader *a)                                 \
    {                                                                                                          \
        return (int32_t)((const ArrayHeader *)a)->count_;                                                      \
    }                                                                                                          \
    void Kotlin_##Name##Array_fillImpl(ObjHeader *a, int32_t from, int32_t to, T v)                            \
    {                                                                                                          \
        ArrayHeader *h = (ArrayHeader *)a;                                                                     \
        checkRangeIndexes(from, to, (int32_t)h->count_);                                                       \
        T *p = (T *)km_array_data(h);                                                                          \
        for (int32_t i = from; i < to; i++)                                                                    \
            p[i] = v;                                                                                          \
    }                                                                                                          \
    void Kotlin_##Name##Array_copyImpl(const ObjHeader *a, int32_t from, ObjHeader *d, int32_t to, int32_t n)  \
    {                                                                                                          \
        copy_check((const ArrayHeader *)a, from, (const ArrayHeader *)d, to, n);                               \
        memmove((T *)km_array_data((ArrayHeader *)d) + to, (T *)km_array_data((ArrayHeader *)a) + from,        \
                (size_t)n * sizeof(T));                                                                        \
    }
KM_PRIM_ARRAY(Boolean, bool)
KM_PRIM_ARRAY(Byte, int8_t)
KM_PRIM_ARRAY(Char, uint16_t)
KM_PRIM_ARRAY(Short, int16_t)
KM_PRIM_ARRAY(Int, int32_t)
KM_PRIM_ARRAY(Long, int64_t)
KM_PRIM_ARRAY(Float, float)
KM_PRIM_ARRAY(Double, double)

ObjHeader *Kotlin_Array_get(const ObjHeader *a, int32_t i, ObjHeader **result)
{
    bounds((const ArrayHeader *)a, i);
    return km_return(result, km_array_refs((ArrayHeader *)a)[i]);
}
KM_NOTHROW ObjHeader *Kotlin_Array_get_without_BoundCheck(const ObjHeader *a, int32_t i, ObjHeader **result)
{
    return km_return(result, km_array_refs((ArrayHeader *)a)[i]);
}
void Kotlin_Array_set(ObjHeader *a, int32_t i, const ObjHeader *v)
{
    bounds((const ArrayHeader *)a, i);
    UpdateHeapRef(&km_array_refs((ArrayHeader *)a)[i], v);
}
KM_NOTHROW void Kotlin_Array_set_without_BoundCheck(ObjHeader *a, int32_t i, const ObjHeader *v)
{
    UpdateHeapRef(&km_array_refs((ArrayHeader *)a)[i], v);
}
KM_NOTHROW int32_t Kotlin_Array_getArrayLength(const ObjHeader *a) { return (int32_t)((const ArrayHeader *)a)->count_; }
void Kotlin_Array_fillImpl(ObjHeader *a, int32_t from, int32_t to, ObjHeader *v)
{
    ArrayHeader *h = (ArrayHeader *)a;
    checkRangeIndexes(from, to, (int32_t)h->count_);
    km_ref_stored();
    for (int32_t i = from; i < to; i++)
        km_array_refs(h)[i] = v;
}
void Kotlin_Array_copyImpl(const ObjHeader *a, int32_t from, ObjHeader *d, int32_t to, int32_t n)
{
    copy_check((const ArrayHeader *)a, from, (const ArrayHeader *)d, to, n);
    km_ref_stored();
    memmove(km_array_refs((ArrayHeader *)d) + to, km_array_refs((ArrayHeader *)a) + from, (size_t)n * sizeof(ObjHeader *));
}
extern const ArrayHeader theEmptyArray;
KM_NOTHROW ObjHeader *Kotlin_emptyArray(ObjHeader **result) { return km_return(result, (ObjHeader *)&theEmptyArray); }

/* Atomic arrays (AtomicIntArray, AtomicLongArray, AtomicArray): the compiler takes the element's address and does the
 * atomic operation there (Natives.cpp). The Kotlin side has already checked the index. */
KM_NOTHROW __attribute__((pure)) int32_t *Kotlin_intArrayGetElementAddress(ObjHeader *a, int32_t index)
{
    return (int32_t *)km_array_data((ArrayHeader *)a) + index;
}
KM_NOTHROW __attribute__((pure)) int64_t *Kotlin_longArrayGetElementAddress(ObjHeader *a, int32_t index)
{
    return (int64_t *)km_array_data((ArrayHeader *)a) + index;
}
KM_NOTHROW __attribute__((pure)) ObjHeader **Kotlin_arrayGetElementAddress(ObjHeader *a, int32_t index)
{
    return km_array_refs((ArrayHeader *)a) + index;
}
