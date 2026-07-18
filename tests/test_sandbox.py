"""Test acoj-sandbox integration with acoj-worker.

Verifies that the sandbox package can compile and run C++ and Python code.
"""

from acoj_sandbox import (
    LanguagesConfig,
    SandboxClient,
    Status,
    compiled_language,
    script_language,
)


def test_cpp_compile_and_run():
    """C++ source compiles and runs, returning AC with correct stdout."""
    languages = LanguagesConfig([
        compiled_language(
            id="cpp17",
            source_filename="main.cpp",
            exe_filename="main",
            compile_argv=["/usr/bin/g++", "-std=c++17", "-O2", "-o", "{exe}", "{source}"],
            run_argv=["{exe}"],
            run_seccomp="none",
        ),
    ])

    client = SandboxClient(languages=languages, transport="subprocess")
    try:
        result = client.run_source(
            language="cpp17",
            source='#include <iostream>\nint main(){std::cout<<"ok\\n";return 0;}',
        )
        assert result.status == Status.AC, f"Expected AC, got {result.status}"
        assert result.compile.exit_code == 0
        assert result.run.exit_code == 0
        assert result.stdout.strip() == "ok"
    finally:
        client.close()


def test_python_script_run():
    """Python source runs and returns AC with correct stdout."""
    languages = LanguagesConfig([
        script_language(
            id="python3",
            source_filename="main.py",
            argv=["/usr/bin/python3", "{source}"],
            seccomp="none",
        ),
    ])

    client = SandboxClient(languages=languages, transport="subprocess")
    try:
        result = client.run_source(
            language="python3",
            source='print("hello from python")',
        )
        assert result.status == Status.AC, f"Expected AC, got {result.status}"
        assert result.run.exit_code == 0
        assert result.stdout.strip() == "hello from python"
    finally:
        client.close()
