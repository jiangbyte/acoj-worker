#!/usr/bin/env python3
from __future__ import annotations

import os
from pathlib import Path

from acoj_sandbox import (
    CommandSpec,
    JudgeLimits,
    LanguageSpec,
    LanguagesConfig,
    SandboxClient,
    Status,
    compiled_language,
    script_language,
)


def main() -> None:
    binary = Path(os.environ["ACOJ_SANDBOX_BINARY"])
    print("binary", binary, binary.exists())
    langs = LanguagesConfig(
        [
            compiled_language(
                id="cpp17",
                compile_argv=["/usr/bin/g++", "-std=c++17", "-O2", "-o", "{exe}", "{source}"],
                run_argv=["{exe}"],
            ),
            script_language(id="python3", argv=["/usr/bin/python3", "{source}"]),
            LanguageSpec(
                id="java17",
                source_filename="Main.java",
                exe_filename="Main",
                compile=CommandSpec(
                    argv=[
                        "/usr/bin/javac",
                        "-J-Xmx192m",
                        "-J-XX:CompressedClassSpaceSize=32m",
                        "-J-XX:+UseSerialGC",
                        "-encoding",
                        "UTF-8",
                        "{source}",
                    ],
                    seccomp="none",
                    memory_limit_check_only=True,
                    limits=JudgeLimits(
                        cpu_time_ms=30000,
                        real_time_ms=60000,
                        processes=256,
                        memory_bytes=512 * 1024 * 1024,
                    ),
                ),
                run=CommandSpec(
                    argv=[
                        "/usr/bin/java",
                        "-Xmx64m",
                        "-Xss256k",
                        "-XX:CompressedClassSpaceSize=32m",
                        "-XX:+UseSerialGC",
                        "-cp",
                        ".",
                        "Main",
                    ],
                    seccomp="none",
                    memory_limit_check_only=True,
                ),
            ),
            LanguageSpec(
                id="go",
                source_filename="main.go",
                exe_filename="main",
                compile=CommandSpec(
                    argv=["/usr/bin/go", "build", "-o", "{exe}", "{source}"],
                    env=["GOCACHE=/tmp/go-cache", "GOPROXY=off", "GO111MODULE=off"],
                    seccomp="none",
                    memory_limit_check_only=True,
                    limits=JudgeLimits(
                        cpu_time_ms=30000,
                        real_time_ms=60000,
                        processes=256,
                        memory_bytes=512 * 1024 * 1024,
                        output_bytes=64 * 1024 * 1024,
                    ),
                ),
                run=CommandSpec(
                    argv=["{exe}"],
                    seccomp="none",
                    memory_limit_check_only=True,
                ),
            ),
        ]
    )
    client = SandboxClient(languages=langs)
    high_mem = JudgeLimits(
        cpu_time_ms=5000,
        real_time_ms=10000,
        processes=256,
        memory_bytes=512 * 1024 * 1024,
        output_bytes=64 * 1024 * 1024,
    )
    cases = [
        ("cpp17", '#include <iostream>\nint main(){std::cout<<"ok\\n";}\n'),
        ("python3", 'print("ok")\n'),
        (
            "java17",
            'public class Main{public static void main(String[] a){System.out.println("ok");}}\n',
        ),
        ("go", 'package main\nimport "fmt"\nfunc main(){fmt.Println("ok")}\n'),
    ]
    for lang, src in cases:
        result = client.run_source(language=lang, source=src, limits=high_mem)
        status = result.status.value if hasattr(result.status, "value") else str(result.status)
        print(lang, status)
        if result.status != Status.AC:
            raise SystemExit(f"FAIL {lang}: {result}")
    print("SANDBOX_OK")


if __name__ == "__main__":
    main()
