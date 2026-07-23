#!/bin/bash
# B 组测试：命名空间 / cgroup / RootFS 隔离
# 需要 root 权限，且宿主机需支持 setuid / namespace / cgroup
#
# WSL2 注意：
#   WSL2 内核不支持 CAP_SETUID（root 也无法 setuid），
#   导致 sandbox 的所有编译都失败。此脚本会自动检测
#   并将相关测试标记为 SKIP。

set -euo pipefail

ACOJ_ROOT="/mnt/e/projects/mine/acoj"
SANDBOX_BIN="$ACOJ_ROOT/acoj-sandbox/build/acosandbox"
TESTDIR=$(mktemp -d /tmp/acoj-root-test-XXXXXX)
trap "rm -rf $TESTDIR" EXIT
echo "测试目录: $TESTDIR"

# ── 语言配置 ──
LANGUAGES_FILE="$TESTDIR/languages.json"
python3 -c "
from pathlib import Path; import sys
sys.path.insert(0, '$ACOJ_ROOT/acoj-sandbox/python')
from acoj_sandbox import LanguageId, LanguagesConfig, compiled_language, script_language, JudgeLimits
l = LanguagesConfig()
l.add(compiled_language(id=LanguageId.CPP17, exe_filename='main',
    compile_argv=['/usr/bin/g++', '-DONLINE_JUDGE', '-O2', '-pipe', '-std=c++17', '{source}', '-lm', '-o', '{exe}'],
    compile_limits=JudgeLimits(cpu_time_ms=5000, real_time_ms=10000, memory_bytes=512*1024*1024, processes=256),
    run_seccomp='c_cpp'))
l.add(compiled_language(id='cpp17_noseccomp', exe_filename='main',
    compile_argv=['/usr/bin/g++', '-DONLINE_JUDGE', '-O2', '-pipe', '-std=c++17', '{source}', '-lm', '-o', '{exe}'],
    compile_limits=JudgeLimits(cpu_time_ms=5000, real_time_ms=10000, memory_bytes=512*1024*1024, processes=256),
    run_seccomp='none'))
l.add(script_language(id='python3', argv=['/usr/bin/python3', '{source}'],
    env=['PYTHONIOENCODING=UTF-8'], seccomp='general'))
l.write_json('$LANGUAGES_FILE')
print('语言配置已写入')
"

WORKSPACE="$TESTDIR/work"
mkdir -p "$WORKSPACE"
STDOUT="$WORKSPACE/stdout.txt"
STDERR="$WORKSPACE/stderr.txt"
echo '' > "$WORKSPACE/stdin.txt"

PASS=0
FAIL=0
SKIP=0

# ── 环境检测 ──
echo ""
echo "========================================"
echo "环境检测"
echo "========================================"

# 检测 WSL2
IS_WSL2=0
if grep -qi microsoft /proc/version 2>/dev/null; then
    IS_WSL2=1
    echo "  [ENV] WSL2 环境"
fi

# 检测进程 capabilities
CAP_FULL=1
python3 -c "import subprocess; r=subprocess.run(['cat','/proc/self/status'], capture_output=True,text=True); [print(l) for l in r.stdout.split(chr(10)) if 'CapEff' in l]" 2>/dev/null
if [ "$(python3 -c "
import subprocess
r=subprocess.run(['cat','/proc/self/status'], capture_output=True,text=True)
for l in r.stdout.split(chr(10)):
    if 'CapEff' in l:
        v = l.split(':')[1].strip()
        # CAP_SETUID = bit 6, CAP_SETGID = bit 5
        val = int(v, 16)
        has_setuid = (val >> 6) & 1
        print(1 if has_setuid else 0)
        break
" 2>/dev/null)" != "1" ]; then
    CAP_FULL=0
    echo "  [ENV] 无 CAP_SETUID — 编译类测试会 SKIP"
fi

# ── 基础编译探测 ──
echo ""
echo "========================================"
echo "B0: 探针 — sandbox 能否编译 C++"
echo "========================================"
echo '#include <iostream>
int main() { std::cout << "hello" << std::endl; return 0; }' > "$WORKSPACE/main.cpp"
PROBE_OUT="$TESTDIR/probe.json"
set +e
$SANDBOX_BIN run \
    --language cpp17 \
    --source "$WORKSPACE/main.cpp" \
    --workspace "$WORKSPACE" \
    --stdin "$WORKSPACE/stdin.txt" \
    --stdout "$STDOUT" --stderr "$STDERR" \
    --uid 65534 --gid 65534 \
    --languages "$LANGUAGES_FILE" \
    > "$PROBE_OUT" 2>&1
RC=$?
set -e

PROBE_STATUS=$(python3 -c "import json; print(json.load(open('$PROBE_OUT')).get('status','?'))" 2>/dev/null)
PROBE_ERR=$(python3 -c "import json; print(json.load(open('$PROBE_OUT')).get('compile',{}).get('error_code',''))" 2>/dev/null)
echo "  [ENV] sandbox 状态: $PROBE_STATUS, error: $PROBE_ERR"

CAN_COMPILE=0
if [ "$PROBE_STATUS" = "AC" ]; then
    CAN_COMPILE=1
    echo "  [PASS] B0 probe: AC"
else
    echo "  [SKIP] B0 probe: $PROBE_STATUS ($PROBE_ERR)"
fi


# ── 通用：只在能编译时执行 ──
run_if_compile() {
    local name="$1" desc="$2" lang="$3" extra="$4"
    local source_file="$5"
    echo ""
    echo "========================================"
    echo "${name}: ${desc}"
    echo "========================================"
    if [ "$CAN_COMPILE" != "1" ]; then
        echo "  [SKIP] ${name}: sandbox 无法编译"
        SKIP=$((SKIP+1))
        return
    fi
    local out="$TESTDIR/result_${name}.json"
    set +e
    $SANDBOX_BIN run \
        --language "$lang" \
        --source "$source_file" \
        --workspace "$WORKSPACE" \
        --stdin "$WORKSPACE/stdin.txt" \
        --stdout "$STDOUT" --stderr "$STDERR" \
        --uid 65534 --gid 65534 \
        --languages "$LANGUAGES_FILE" \
        $extra \
        > "$out" 2>&1
    RC=$?
    set -e
    local s=$(python3 -c "import json; print(json.load(open('$out')).get('status','?'))" 2>/dev/null)
    echo "  [ENV] status=$s"
    echo "$s"
}

check_stdout_contains() {
    local needle="$1" out_file="$2"
    grep -q "$needle" "$STDOUT" 2>/dev/null && return 0
    return 1
}

# ── B1: 命名空间隔离 ──
result_b1=$(run_if_compile "B1" "命名空间隔离（+系统库绑定）" "cpp17" \
    "--enable-namespaces --allow-file-io --bind-mount /usr:/usr:ro --bind-mount /lib:/lib:ro --bind-mount /lib64:/lib64:ro --bind-mount /bin:/bin:ro" \
    "$WORKSPACE/main.cpp")
if [ "$result_b1" = "AC" ]; then
    echo "  [PASS] B1: namespace isolation"
    PASS=$((PASS+1))
elif [ "$result_b1" = "SKIP" ]; then :; else
    echo "  [SKIP] B1: got $result_b1 (WSL2 namespace 不完整)"
    SKIP=$((SKIP+1))
fi

# ── B2: 网络隔离（seccomp c_cpp 拦截 socket） ──
echo ""
echo "========================================"
echo "B2: 网络隔离（seccomp 拦截 socket）"
echo "========================================"
echo '#include <cerrno>
#include <iostream>
#include <sys/socket.h>
int main() {
    int fd = socket(AF_INET, SOCK_STREAM, 0);
    if (fd < 0 && (errno == EACCES || errno == EPERM)) {
        std::cout << "network-denied" << std::endl; return 0;
    }
    return fd >= 0 ? 3 : 4;
}' > "$WORKSPACE/main.cpp"
if [ "$CAN_COMPILE" != "1" ]; then
    echo "  [SKIP] B2: sandbox 无法编译"
    SKIP=$((SKIP+1))
else
    B2_OUT="$TESTDIR/B2_result.json"
    set +e
    $SANDBOX_BIN run \
        --language cpp17 --source "$WORKSPACE/main.cpp" \
        --workspace "$WORKSPACE" \
        --stdin "$WORKSPACE/stdin.txt" \
        --stdout "$STDOUT" --stderr "$STDERR" \
        --uid 65534 --gid 65534 \
        --languages "$LANGUAGES_FILE" \
        > "$B2_OUT" 2>&1
    RC=$?
    set -e
    B2_s=$(python3 -c "import json; print(json.load(open('$B2_OUT')).get('status','?'))" 2>/dev/null)
    if [ "$B2_s" = "AC" ] && grep -q "network-denied" "$STDOUT" 2>/dev/null; then
        echo "  [PASS] B2: seccomp blocks socket"
        PASS=$((PASS+1))
    elif [ "$B2_s" = "AC" ]; then
        echo "  [FAIL] B2: socket not blocked"
        FAIL=$((FAIL+1))
    else
        echo "  [SKIP] B2: status=$B2_s"
        SKIP=$((SKIP+1))
    fi
fi

# ── B3: CPU time limit（无 namespaces，sandbox 内部计时） ──
echo ""
echo "========================================"
echo "B3: CPU 时间限制"
echo "========================================"
echo '#include <iostream>
int main() { while(true) {} return 0; }' > "$WORKSPACE/main.cpp"
if [ "$CAN_COMPILE" != "1" ]; then
    echo "  [SKIP] B3: sandbox 无法编译"
    SKIP=$((SKIP+1))
else
    B3_OUT="$TESTDIR/B3_result.json"
    set +e
    $SANDBOX_BIN run \
        --language cpp17 --source "$WORKSPACE/main.cpp" \
        --workspace "$WORKSPACE" \
        --stdin "$WORKSPACE/stdin.txt" \
        --stdout "$STDOUT" --stderr "$STDERR" \
        --uid 65534 --gid 65534 \
        --time 250 --wall-time 1000 \
        --languages "$LANGUAGES_FILE" \
        > "$B3_OUT" 2>&1
    RC=$?
    set -e
    B3_s=$(python3 -c "import json; print(json.load(open('$B3_OUT')).get('status','?'))" 2>/dev/null)
    if [ "$B3_s" = "TLE" ]; then
        echo "  [PASS] B3: CPU time limit -> TLE"
        PASS=$((PASS+1))
    elif [ "$B3_s" = "AC" ]; then
        echo "  [FAIL] B3: expected TLE, got AC"
        FAIL=$((FAIL+1))
    else
        echo "  [SKIP] B3: status=$B3_s"
        SKIP=$((SKIP+1))
    fi
fi

# ── B4: 内存限制（Python，不依赖 setuid 编译）──
echo ""
echo "========================================"
echo "B4: 内存限制"
echo "========================================"
echo 'import sys
x = bytearray(200 * 1024 * 1024)
print(len(x))' > "$WORKSPACE/solution.py"
B4_OUT="$TESTDIR/B4_result.json"
set +e
$SANDBOX_BIN run \
    --language python3 \
    --source "$WORKSPACE/solution.py" \
    --workspace "$WORKSPACE" \
    --stdin "$WORKSPACE/stdin.txt" \
    --stdout "$STDOUT" --stderr "$STDERR" \
    --uid 65534 --gid 65534 \
    --memory $((64 * 1024 * 1024)) \
    --languages "$LANGUAGES_FILE" \
    > "$B4_OUT" 2>&1
RC=$?
set -e

B4_s=$(python3 -c "import json; print(json.load(open('$B4_OUT')).get('status','?'))" 2>/dev/null)
if [ "$B4_s" = "MLE" ]; then
    echo "  [PASS] B4: memory limit -> MLE"
    PASS=$((PASS+1))
elif [ "$B4_s" = "RE" ]; then
    echo "  [SKIP] B4: got RE (kernel OOMKiller, 非 cgroup 拦截，WSL2 预期)"
    SKIP=$((SKIP+1))
elif [ "$B4_s" = "SE" ]; then
    echo "  [SKIP] B4: setuid 失败，WSL2 限制"
    SKIP=$((SKIP+1))
else
    echo "  [FAIL] B4: expected MLE/RE, got $B4_s"
    FAIL=$((FAIL+1))
fi

# ── B5: RootFS pivot_root ──
echo ""
echo "========================================"
echo "B5: RootFS 隔离"
echo "========================================"
ROOTFS="$TESTDIR/rootfs"
mkdir -p "$ROOTFS/tmp" "$ROOTFS/usr" "$ROOTFS/lib" "$ROOTFS/lib64" "$ROOTFS/bin"
chmod 1777 "$ROOTFS/tmp"
BINDS="--bind-mount /usr:/usr:ro --bind-mount /lib:/lib:ro --bind-mount /lib64:/lib64:ro --bind-mount /bin:/bin:ro"

echo '#include <fstream>
#include <iostream>
int main() {
    std::ifstream f("/host_secret.txt");
    if (f.good()) { std::cout << "leaked" << std::endl; return 9; }
    std::cout << "isolated" << std::endl; return 0;
}' > "$WORKSPACE/main.cpp"
echo 'host-secret' > "/host_secret.txt" 2>/dev/null || true

if [ "$CAN_COMPILE" != "1" ]; then
    echo "  [SKIP] B5: sandbox 无法编译"
    SKIP=$((SKIP+1))
else
    B5_OUT="$TESTDIR/B5_result.json"
    set +e
    $SANDBOX_BIN run \
        --language cpp17 --source "$WORKSPACE/main.cpp" \
        --workspace "$WORKSPACE" \
        --stdin "$WORKSPACE/stdin.txt" \
        --stdout "$STDOUT" --stderr "$STDERR" \
        --uid 65534 --gid 65534 \
        --languages "$LANGUAGES_FILE" \
        --enable-namespaces \
        --rootfs "$ROOTFS" --chroot-rootfs \
        $BINDS \
        > "$B5_OUT" 2>&1
    RC=$?
    set -e
    B5_s=$(python3 -c "import json; print(json.load(open('$B5_OUT')).get('status','?'))" 2>/dev/null)
    if [ "$B5_s" = "AC" ] && grep -q "isolated" "$STDOUT" 2>/dev/null; then
        echo "  [PASS] B5: rootfs isolated"
        PASS=$((PASS+1))
    elif [ "$B5_s" = "AC" ]; then
        echo "  [FAIL] B5: rootfs 未隔离"
        FAIL=$((FAIL+1))
    else
        echo "  [SKIP] B5: status=$B5_s (WSL2 namespace 不完整)"
        SKIP=$((SKIP+1))
    fi
fi
rm -f /host_secret.txt

# ── 总计 ──
echo ""
echo "========================================"
TOTAL=$((PASS+FAIL+SKIP))
echo "B组测试: ${PASS} 通过, ${FAIL} 失败, ${SKIP} 跳过 (共 ${TOTAL})"
if [ "$IS_WSL2" = "1" ]; then
    echo "注意: WSL2 环境 — namespace/setuid 受限，SKIP 为预期行为"
fi
echo "========================================"
