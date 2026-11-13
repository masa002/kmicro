// Interface dispatch through LookupInterfaceTableRecord: class All implements 40 interfaces, more than the 32
// colours a fast interface table has room for, so the compiler emits the slow lookup on every interface call and
// type check, and gives All (and the small classes whose interface ids collide) a sorted table instead.

interface I0 { fun f0(): Int }
interface I1 { fun f1(): Int }
interface I2 { fun f2(): Int }
interface I3 { fun f3(): Int }
interface I4 { fun f4(): Int }
interface I5 { fun f5(): Int }
interface I6 { fun f6(): Int }
interface I7 { fun f7(): Int }
interface I8 { fun f8(): Int }
interface I9 { fun f9(): Int }
interface I10 { fun f10(): Int }
interface I11 { fun f11(): Int }
interface I12 { fun f12(): Int }
interface I13 { fun f13(): Int }
interface I14 { fun f14(): Int }
interface I15 { fun f15(): Int }
interface I16 { fun f16(): Int }
interface I17 { fun f17(): Int }
interface I18 { fun f18(): Int }
interface I19 { fun f19(): Int }
interface I20 { fun f20(): Int }
interface I21 { fun f21(): Int }
interface I22 { fun f22(): Int }
interface I23 { fun f23(): Int }
interface I24 { fun f24(): Int }
interface I25 { fun f25(): Int }
interface I26 { fun f26(): Int }
interface I27 { fun f27(): Int }
interface I28 { fun f28(): Int }
interface I29 { fun f29(): Int }
interface I30 { fun f30(): Int }
interface I31 { fun f31(): Int }
interface I32 { fun f32(): Int }
interface I33 { fun f33(): Int }
interface I34 { fun f34(): Int }
interface I35 { fun f35(): Int }
interface I36 { fun f36(): Int }
interface I37 { fun f37(): Int }
interface I38 { fun f38(): Int }
interface I39 { fun f39(): Int }

class All : I0, I1, I2, I3, I4, I5, I6, I7, I8, I9, I10, I11, I12, I13, I14, I15, I16, I17, I18, I19, I20, I21, I22, I23, I24, I25, I26, I27, I28, I29, I30, I31, I32, I33, I34, I35, I36, I37, I38, I39 {
    override fun f0() = 1
    override fun f1() = 4
    override fun f2() = 7
    override fun f3() = 10
    override fun f4() = 13
    override fun f5() = 16
    override fun f6() = 19
    override fun f7() = 22
    override fun f8() = 25
    override fun f9() = 28
    override fun f10() = 31
    override fun f11() = 34
    override fun f12() = 37
    override fun f13() = 40
    override fun f14() = 43
    override fun f15() = 46
    override fun f16() = 49
    override fun f17() = 52
    override fun f18() = 55
    override fun f19() = 58
    override fun f20() = 61
    override fun f21() = 64
    override fun f22() = 67
    override fun f23() = 70
    override fun f24() = 73
    override fun f25() = 76
    override fun f26() = 79
    override fun f27() = 82
    override fun f28() = 85
    override fun f29() = 88
    override fun f30() = 91
    override fun f31() = 94
    override fun f32() = 97
    override fun f33() = 100
    override fun f34() = 103
    override fun f35() = 106
    override fun f36() = 109
    override fun f37() = 112
    override fun f38() = 115
    override fun f39() = 118
}

class S0 : I0, I32 {
    override fun f0() = 1000
    override fun f32() = 1032
}
class S1 : I1, I33 {
    override fun f1() = 2001
    override fun f33() = 2033
}
class S2 : I2, I34 {
    override fun f2() = 3002
    override fun f34() = 3034
}
class S3 : I3, I35 {
    override fun f3() = 4003
    override fun f35() = 4035
}
class S4 : I4, I36 {
    override fun f4() = 5004
    override fun f36() = 5036
}
class S5 : I5, I37 {
    override fun f5() = 6005
    override fun f37() = 6037
}
class S6 : I6, I38 {
    override fun f6() = 7006
    override fun f38() = 7038
}
class S7 : I7, I39 {
    override fun f7() = 8007
    override fun f39() = 8039
}
class S8 : I0, I16, I32 {
    override fun f0() = 9000
    override fun f16() = 9016
    override fun f32() = 9032
}
class S9 : I1, I17, I33 {
    override fun f1() = 10001
    override fun f17() = 10017
    override fun f33() = 10033
}
class S10 : I2, I18, I34 {
    override fun f2() = 11002
    override fun f18() = 11018
    override fun f34() = 11034
}
class S11 : I3, I19, I35 {
    override fun f3() = 12003
    override fun f19() = 12019
    override fun f35() = 12035
}
class S12 : I0, I1, I2, I3, I4, I5, I6, I7, I8, I9, I33, I34 {
    override fun f0() = 13000
    override fun f1() = 13001
    override fun f2() = 13002
    override fun f3() = 13003
    override fun f4() = 13004
    override fun f5() = 13005
    override fun f6() = 13006
    override fun f7() = 13007
    override fun f8() = 13008
    override fun f9() = 13009
    override fun f33() = 13033
    override fun f34() = 13034
}

fun probe(x: Any): String {
    val hits = StringBuilder()
    if (x is I0) hits.append(' ').append(x.f0())
    if (x is I1) hits.append(' ').append(x.f1())
    if (x is I2) hits.append(' ').append(x.f2())
    if (x is I3) hits.append(' ').append(x.f3())
    if (x is I4) hits.append(' ').append(x.f4())
    if (x is I5) hits.append(' ').append(x.f5())
    if (x is I6) hits.append(' ').append(x.f6())
    if (x is I7) hits.append(' ').append(x.f7())
    if (x is I8) hits.append(' ').append(x.f8())
    if (x is I9) hits.append(' ').append(x.f9())
    if (x is I10) hits.append(' ').append(x.f10())
    if (x is I11) hits.append(' ').append(x.f11())
    if (x is I12) hits.append(' ').append(x.f12())
    if (x is I13) hits.append(' ').append(x.f13())
    if (x is I14) hits.append(' ').append(x.f14())
    if (x is I15) hits.append(' ').append(x.f15())
    if (x is I16) hits.append(' ').append(x.f16())
    if (x is I17) hits.append(' ').append(x.f17())
    if (x is I18) hits.append(' ').append(x.f18())
    if (x is I19) hits.append(' ').append(x.f19())
    if (x is I20) hits.append(' ').append(x.f20())
    if (x is I21) hits.append(' ').append(x.f21())
    if (x is I22) hits.append(' ').append(x.f22())
    if (x is I23) hits.append(' ').append(x.f23())
    if (x is I24) hits.append(' ').append(x.f24())
    if (x is I25) hits.append(' ').append(x.f25())
    if (x is I26) hits.append(' ').append(x.f26())
    if (x is I27) hits.append(' ').append(x.f27())
    if (x is I28) hits.append(' ').append(x.f28())
    if (x is I29) hits.append(' ').append(x.f29())
    if (x is I30) hits.append(' ').append(x.f30())
    if (x is I31) hits.append(' ').append(x.f31())
    if (x is I32) hits.append(' ').append(x.f32())
    if (x is I33) hits.append(' ').append(x.f33())
    if (x is I34) hits.append(' ').append(x.f34())
    if (x is I35) hits.append(' ').append(x.f35())
    if (x is I36) hits.append(' ').append(x.f36())
    if (x is I37) hits.append(' ').append(x.f37())
    if (x is I38) hits.append(' ').append(x.f38())
    if (x is I39) hits.append(' ').append(x.f39())
    return hits.toString()
}

fun main() {
    val objects: List<Any> = listOf(All(), S0(), S1(), S2(), S3(), S4(), S5(), S6(), S7(), S8(), S9(), S10(), S11(), S12(), "text", listOf(1), 42)
    for (x in objects) println("${x::class.simpleName}:${probe(x)}")
    val calls: List<I0> = objects.filterIsInstance<I0>()
    println("I0 calls: ${calls.map { it.f0() }}")
    val i33: List<I33> = objects.filterIsInstance<I33>()
    println("I33 calls: ${i33.map { it.f33() }}")
}
