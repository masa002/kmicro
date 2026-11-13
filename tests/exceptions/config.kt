// A file whose global fails to initialise: its first use throws FileFailedToInitializeException, caused by the
// initializer's exception (uncaught.kt, failedInitializer).
val config: Int = loadConfig()

fun loadConfig(): Int = throw IllegalStateException("config block missing")
