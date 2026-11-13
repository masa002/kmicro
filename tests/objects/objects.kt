@file:OptIn(kotlin.experimental.ExperimentalNativeApi::class)
import kotlin.native.CName

interface Shape { fun area(): Int }
open class Rect(val w: Int, val h: Int) : Shape { override fun area() = w * h }
class Square(s: Int) : Rect(s, s)
class Tri(val b: Int, val h: Int) : Shape { override fun area() = b * h / 2 }

@CName("k_entry")
fun entry(n: Int): Int {
    val shapes = arrayOf<Shape>(Rect(n, 2), Square(n), Tri(n, 4))
    var sum = 0
    for (s in shapes) sum += s.area()
    return sum
}
