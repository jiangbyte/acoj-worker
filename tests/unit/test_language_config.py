"""语言配置构建单元测试 — build_languages_config。"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from app.modules.judge.language_config import build_languages_config


def test_compiled_language_build():
    """compile_command 非空 → compiled_language, compile 不为 None。"""
    cfg = build_languages_config({
        "key": "cpp17",
        "compile_command": "g++ -O2 -o {exe} {source}",
        "run_command": "{exe}",
    })
    assert cfg is not None
    spec = cfg.get("cpp17")
    assert spec is not None
    # compiled_language: compile.CommandSpec exists and has limits
    assert spec.compile is not None
    assert spec.compile.limits is not None


def test_script_language_build():
    """compile_command 为空 → script_language, compile 为 None。"""
    cfg = build_languages_config({
        "key": "python3",
        "compile_command": "",
        "run_command": "/usr/bin/python3 {source}",
    })
    spec = cfg.get("python3")
    assert spec is not None
    # script_language: compile is None
    assert spec.compile is None


def test_custom_exe_filename():
    """exe_filename='interactor' 正确传递。"""
    cfg = build_languages_config(
        {"key": "cpp17", "compile_command": "g++ -o {exe} {source}", "run_command": "{exe}"},
        exe_filename="interactor",
    )
    spec = cfg.get("cpp17")
    assert spec is not None


def test_run_argv_with_placeholders():
    """run_command 含 {source}/{exe} → 参数列表正确。"""
    cfg = build_languages_config({
        "key": "py3",
        "compile_command": "",
        "run_command": "/usr/bin/python3 {source}",
    })
    spec = cfg.get("py3")
    assert spec is not None


def test_empty_compile_with_whitespace():
    """compile_command='  ' → 视为空，compile 为 None。"""
    cfg = build_languages_config({
        "key": "script",
        "compile_command": "  ",
        "run_command": "/bin/sh {source}",
    })
    spec = cfg.get("script")
    assert spec is not None
    assert spec.compile is None
