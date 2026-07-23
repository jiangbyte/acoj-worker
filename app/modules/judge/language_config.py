"""语言配置构建：从 MQ payload 中的 language dict 生成 acoj_sandbox 配置。"""

import shlex

from acoj_sandbox import JudgeLimits, LanguagesConfig, compiled_language, script_language


def build_languages_config(language: dict, *, exe_filename: str = "main") -> LanguagesConfig:
    """从 MQ payload 中的 language dict 构建 LanguagesConfig。"""
    language_key = language["key"]
    compile_cmd = language.get("compile_command") or ""

    if compile_cmd.strip():
        compile_argv = shlex.split(compile_cmd)
        run_argv = shlex.split(language.get("run_command") or "{exe}")
        spec = compiled_language(
            id=language_key,
            exe_filename=exe_filename,
            compile_argv=compile_argv,
            run_argv=run_argv,
            compile_limits=JudgeLimits(
                cpu_time_ms=30000,
                real_time_ms=60000,
                processes=256,
                memory_bytes=1024 * 1024 * 1024,
            ),
        )
    else:
        run_argv = shlex.split(language.get("run_command") or "")
        spec = script_language(id=language_key, argv=run_argv)

    return LanguagesConfig([spec])
