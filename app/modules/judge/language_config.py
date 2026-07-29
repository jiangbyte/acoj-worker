"""语言配置构建：从 MQ payload 中的 language dict 生成 acoj_sandbox 配置。"""

import shlex

from acoj_sandbox import (
    CommandSpec,
    JudgeLimits,
    LanguageSpec,
    LanguagesConfig,
    compiled_language,
    script_language,
)


def _needs_virt_as(language_key: str) -> bool:
    """JVM / Go runtime need large virtual address space; avoid RLIMIT_AS."""
    key = (language_key or "").strip().lower()
    return key.startswith("java") or key in {"go", "golang"}


def _default_exe_filename(language_key: str, exe_filename: str) -> str:
    key = (language_key or "").strip().lower()
    if key.startswith("java"):
        return "Main"
    return exe_filename


def build_languages_config(language: dict, *, exe_filename: str = "main") -> LanguagesConfig:
    """从 MQ payload 中的 language dict 构建 LanguagesConfig。"""
    language_key = language["key"]
    compile_cmd = language.get("compile_command") or ""
    exe_name = _default_exe_filename(language_key, exe_filename)

    if compile_cmd.strip():
        compile_argv = shlex.split(compile_cmd)
        run_argv = shlex.split(language.get("run_command") or "{exe}")
        compile_limits = JudgeLimits(
            cpu_time_ms=30000,
            real_time_ms=60000,
            processes=256,
            memory_bytes=1024 * 1024 * 1024,
            output_bytes=64 * 1024 * 1024,
        )
        if _needs_virt_as(language_key):
            key_l = language_key.strip().lower()
            compile_env: list[str] = []
            run_env: list[str] = []
            if key_l in {"go", "golang"}:
                compile_env = [
                    "GOCACHE=/tmp/go-cache",
                    "GOPROXY=off",
                    "GO111MODULE=off",
                    "HOME=/tmp",
                ]
            elif key_l.startswith("java"):
                java_home = "/usr/lib/jvm/java-17-openjdk-amd64"
                java_env = [
                    f"JAVA_HOME={java_home}",
                    f"LD_LIBRARY_PATH={java_home}/lib",
                ]
                compile_env = list(java_env)
                run_env = list(java_env)
            spec = LanguageSpec(
                id=language_key,
                source_filename=language.get("source_filename")
                or ("Main.java" if key_l.startswith("java") else "main.go"),
                exe_filename=exe_name,
                compile=CommandSpec(
                    argv=compile_argv,
                    env=compile_env,
                    seccomp="none",
                    memory_limit_check_only=True,
                    limits=compile_limits,
                ),
                run=CommandSpec(
                    argv=run_argv,
                    env=run_env,
                    seccomp="none",
                    memory_limit_check_only=True,
                ),
            )
        else:
            spec = compiled_language(
                id=language_key,
                exe_filename=exe_name,
                compile_argv=compile_argv,
                run_argv=run_argv,
                compile_limits=compile_limits,
            )
    else:
        run_argv = shlex.split(language.get("run_command") or "")
        spec = script_language(id=language_key, argv=run_argv)

    return LanguagesConfig([spec])
