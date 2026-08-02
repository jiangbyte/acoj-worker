# 判题协议（Celery）

实现：`app/modules/judge/schemas.py`、`tasks.py`。

## 总览

| 项 | 值 |
|----|-----|
| Task | `judge.execute` |
| Queue | `judge`（`JUDGE__TASK_DEFAULT_QUEUE` / `CELERY__WORKER_QUEUES`） |
| 入参 | `JudgePayload` |
| 返回 | `JudgeResultOut` |
| Broker | `CELERY__BROKER_URL`（Redis，建议独立 DB） |
| Result | 默认 `REDIS__URL`；可用 `CELERY__RESULT_BACKEND` |

```python
async_result = celery_app.send_task("judge.execute", args=[payload], queue="judge")
result = async_result.get(timeout=60)
```

辅助：`tests/judge_helper.py`。FILE 测例与 worker 共用 `STORAGE__*`。

---

## 请求：JudgePayload

```json
{
  "submission_id": "<id>",
  "judge_mode": "STANDARD",
  "problem": {
    "code": "P1000",
    "time_limit_ms": 2000,
    "memory_limit_kb": 262144,
    "points": 100.0,
    "partial": false
  },
  "language": {
    "key": "cpp17",
    "name": "C++17",
    "extension": ".cpp",
    "compile_command": "/usr/bin/g++ -std=c++17 -O2 -o {exe} {source}",
    "run_command": "{exe}"
  },
  "source": "<源代码>",
  "test_cases": []
}
```

| 字段 | 说明 |
|------|------|
| `source` | 用户源码 |
| `judge_mode` | `STANDARD` \| `SPECIAL_JUDGE` \| `INTERACTIVE` |
| `language.compile_command` | 空 → 解释型 |
| `compile_command` / `run_command` | `{source}` `{exe}`；建议绝对路径 |
| `problem.partial` | `false` 且无 `batch_no` → ACM；`true` → OI |

### test_cases

| 字段 | 说明 |
|------|------|
| `case_no` / `points` | 编号与分值 |
| `time_limit_ms` / `memory_limit_kb` | 可覆盖题目默认 |
| `input_inline` / `output_inline` | 内联 |
| `input_file` / `output_file` | 对象 key + `input_sha256` / `output_sha256` |
| `batch_no` / `batch_depends` | IOI |

默认输出上限 8MiB（`output_limit_bytes` 可覆盖）。

### FILE

- 每测例一对 `.in` / `.out`（或 `.ans`）
- key 例：`oj/problem/{problem_id}/testdata/1.in`
- 带 sha256；变更用新 key；与 API 同 bucket
- 样例可用 inline；正式题用 FILE
- 对象不可用 → `status=FAILED`

### STANDARD

编译 → 运行 → 全文比对（忽略行尾空白）→ ACM / OI / IOI。

### SPECIAL_JUDGE

```json
{
  "judge_mode": "SPECIAL_JUDGE",
  "spj": {
    "language": { "key": "cpp17", "compile_command": "...", "run_command": "{exe}" },
    "source": "<checker 源码>"
  }
}
```

Checker 参数：input / user_out / answer；exit 0=AC。测例支持 FILE。

### INTERACTIVE

```json
{
  "judge_mode": "INTERACTIVE",
  "interactor": {
    "language": { "key": "cpp17", "compile_command": "...", "run_command": "{exe}" },
    "source": "<交互器源码>",
    "time_limit_ms": 4000,
    "memory_limit_kb": 262144
  }
}
```

FIFO 互联；交互器 stderr 为评测信息；exit 0=AC，1=WA。输入支持 FILE。

---

## 响应：JudgeResultOut

```json
{
  "submission_id": "<id>",
  "status": "COMPLETED",
  "result": "AC",
  "score": 100.0,
  "time_ms": 42,
  "memory_kb": 4096,
  "compile_time_ms": 380,
  "compile_memory_kb": 65536,
  "compile_output": "",
  "compile_error": false,
  "cases": [
    {
      "case_no": 1,
      "result": "AC",
      "time_ms": 10,
      "memory_kb": 2048,
      "points": 100.0,
      "stdout_preview": "",
      "stderr_preview": ""
    }
  ],
  "error": null,
  "wall_time_ms": 120
}
```

失败：`status=FAILED`，`error` 说明原因。

| 字段 | 含义 |
|------|------|
| `time_ms` | 各点运行时间之和 |
| `memory_kb` | 各点 RSS 峰值的最大值 |
| `compile_time_ms` / `compile_memory_kb` | 编译 |
| `cases[].time_ms` | 该点；TLE 为 max(CPU, wall) |
| `cases[].memory_kb` | 该点 RSS |
| `wall_time_ms` | 整次墙钟 |

`result`：`AC` `WA` `TLE` `MLE` `RE` `CE` `SE` `IE` `OLE` 等。  
`cases[]` 字段：`case_no` `result` `time_ms` `memory_kb` `points` `stdout_preview` `stderr_preview`。

---

## 语言与镜像

| key | 工具 |
|-----|------|
| `cpp17` 等 | `/usr/bin/g++` |
| `python3` | `/usr/bin/python3` |
| `java17` | OpenJDK 17 |
| `go` | `/usr/bin/go` |

`language_config.py`：Java/Go 使用 `memory_limit_check_only`；Go 注入 `HOME`/`GOCACHE`；Java 注入 `JAVA_HOME`；编译 `output_bytes` 较大。命令非 shell，环境由配置注入。

```text
compile: /usr/bin/javac -J-Xmx192m -J-XX:CompressedClassSpaceSize=32m -J-XX:+UseSerialGC -encoding UTF-8 {source}
run:     /usr/bin/java -Xmx64m -Xss256k -XX:CompressedClassSpaceSize=32m -XX:+UseSerialGC -cp . Main
```

---

## 运维

- 队列：`judge,default`；节点名唯一。
- Prefetch：`JUDGE__WORKER_PREFETCH_MULTIPLIER`（亦可用 `CELERY__WORKER_PREFETCH_MULTIPLIER`）。
- 隔离：namespaces、cgroup、`JUDGE__SANDBOX_ROOTFS_PATH`；Docker：`--privileged --cgroupns=host`。
- Rootfs：`/opt/acoj-rootfs` + bind `/usr` `/etc` `/proc`；`pivot_root` put_old 为 `.old_root.<pid>`。
- 吞吐：`--cpus` 与 concurrency 对齐；多副本扩展。
