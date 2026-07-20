"""将 MQ 消息中的语言配置映射为 sandbox LanguageSpec。"""

import shlex

from acoj_sandbox import (
    JudgeLimits,
    LanguagesConfig,
    compiled_language,
    script_language,
)


def _default_extension(language_key: str) -> str:
    extensions = {
        "c99": ".c",
        "c11": ".c",
        "c17": ".c",
        "cpp98": ".cpp",
        "cpp11": ".cpp",
        "cpp14": ".cpp",
        "cpp17": ".cpp",
        "cpp20": ".cpp",
        "python2": ".py",
        "python3": ".py",
        "pypy2": ".py",
        "pypy3": ".py",
        "java8": ".java",
        "java11": ".java",
        "java17": ".java",
        "go": ".go",
        "nodejs": ".js",
        "rust": ".rs",
        "ruby": ".rb",
        "php": ".php",
        "perl": ".pl",
        "lua": ".lua",
        "haskell": ".hs",
        "kotlin": ".kt",
        "scala": ".scala",
        "swift": ".swift",
    }
    return extensions.get(language_key, ".txt")


def _parse_argv(cmd: str | None) -> list[str]:
    if not cmd or not cmd.strip():
        return []
    try:
        return shlex.split(cmd)
    except ValueError:
        return cmd.split()


def build_languages_config(language: dict, *, exe_filename: str | None = None) -> LanguagesConfig:
    language_key = language["key"]
    extension = language.get("extension") or _default_extension(language_key)
    source_filename = f"main{extension}"

    compile_cmd = language.get("compile_command") or ""
    if compile_cmd.strip():
        compile_argv = _parse_argv(compile_cmd)
        run_argv = _parse_argv(language.get("run_command")) if language.get("run_command") else ["{exe}"]
        spec = compiled_language(
            id=language_key,
            source_filename=source_filename,
            exe_filename=exe_filename or "main",
            compile_argv=compile_argv,
            run_argv=run_argv,
            compile_limits=JudgeLimits(cpu_time_ms=30000, real_time_ms=60000, processes=256, memory_bytes=1024*1024*1024),
            run_seccomp="none",
        )
    else:
        run_argv = _parse_argv(language.get("run_command")) if language.get("run_command") else []
        spec = script_language(
            id=language_key,
            source_filename=source_filename,
            argv=run_argv,
            seccomp="none",
        )

    return LanguagesConfig([spec])
