# Security policy

## Supported versions

The latest release and the `main` branch. A fix goes into `main` and into the next release; earlier releases are not
updated.

## Reporting a vulnerability

Report it privately, through GitHub's private vulnerability reporting: open the repository's **Security** tab and
choose **Report a vulnerability** (<https://github.com/masa002/kmicro/security/advisories/new>). Please do not open a
public issue, pull request or discussion for it.

Say what is affected (a runtime file, a tool, a build step), how to reproduce it (the program, the commands, the
output) and what an attacker gains. The report stays private while it is worked on. Once it is fixed, the advisory
is published with the fix, crediting you unless you ask not to be named.

## Scope

In scope: the runtime in `runtime/` (for example memory corruption that Kotlin code or C code using the documented
API can cause), the build tools in `toolchain/` and `tools/`, and the examples and board files in this repository.

Out of scope: Kotlin/Native, LLVM, the xPack GCC and QEMU themselves (report those to their projects), and a
firmware built with kmicro that is not part of this repository.
