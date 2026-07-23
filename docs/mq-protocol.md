# Worker MQ 数据协议说明

## 整体架构

```
acoj (API 服务)
  │  POST /portal/submission
  │  → service_portal.py 构建 JudgeRequest dict
  │  → event_producer.publish() 发送到 RabbitMQ
  │
  ▼  RabbitMQ exchange="oj.judge" (direct, durable)
  │   routing_key="request"
  │
acoj-worker (Celery Worker)
  │  Celery task "judge.execute" 消费
  │  → orchestrator.judge() 派发到三种模式
  │  → SandboxClient 执行用户代码
  │  → 返回 JudgeResultOut dict
  │
  ▼  (当前: Celery return value → Redis backend)
  │  (预留: 可直接 publish 到 RabbitMQ exchange="oj.judge" routing_key="result")
  │
acoj (API 服务)
  │  judge_result_consumer.py 监听 queue="oj.judge.result"
  │  → 解析 JSON → 写入 OjSubmission + OjSubmissionCase
```

关键配置：
- `MQ__ENABLED=false` 默认关闭 MQ 消费者（结果回写走 Celery）
- `CELERY__BROKER_URL` 和 `MQ__URL` 共用同一个 RabbitMQ

---

## 一、判题请求消息（API → Worker）

### RabbitMQ 拓扑

| 项目 | 值 |
|------|-----|
| Exchange | `oj.judge` |
| Exchange 类型 | `direct` |
| 持久化 | `durable=True` |
| Routing Key | `request` |
| Content-Type | `application/json` |
| Delivery Mode | 2（持久化） |

### Payload 结构

消息体为 JSON dict，由 `service_portal.py::_build_judge_request()` 构建，对应 worker 侧 Pydantic 模型 `JudgePayload`（`schemas.py`）。

#### 必填字段（所有判题模式）

```json
{
  "submission_id": "<snowflake-id>",
  "judge_mode": "STANDARD",
  "problem": {
    "code": "<problem_code>",
    "time_limit_ms": 2000,
    "memory_limit_kb": 262144,
    "points": 100.0,
    "partial": false
  },
  "language": {
    "key": "cpp17",
    "name": "C++17",
    "extension": ".cpp",
    "compile_command": "g++ -O2 -std=c++17 {src} -o {exe}",
    "run_command": "{exe}"
  },
  "source": "<用户源代码>",
  "test_cases": [...]
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `submission_id` | string | Snowflake ID，唯一标识一次提交 |
| `judge_mode` | string | 判题模式：`STANDARD` / `SPECIAL_JUDGE` / `INTERACTIVE` |
| `problem.code` | string | 题目标识码 |
| `problem.time_limit_ms` | int | 默认时间限制（毫秒），单 case 可覆盖 |
| `problem.memory_limit_kb` | int | 默认内存限制（KB），单 case 可覆盖 |
| `problem.points` | float | 题目总分 |
| `problem.partial` | bool | 是否允许部分得分（影响 ACM 模式是否首错停止） |
| `language.key` | string | 语言标识（如 `cpp17`、`python3`） |
| `language.compile_command` | string\|null | 编译命令模板，`null` 表示解释型语言 |
| `language.run_command` | string\|null | 运行命令模板 |
| `source` | string | 用户程序源代码 |

#### test_cases 结构

```json
{
  "case_no": 1,
  "points": 33.33,
  "time_limit_ms": 1000,
  "memory_limit_kb": 131072,
  "input_file": "testdata/input_1.txt",
  "output_file": "testdata/output_1.txt",
  "input_inline": "1 2\n",
  "output_inline": "3\n",
  "input_sha256": "<hash>",
  "output_sha256": "<hash>",
  "batch_no": 1,
  "batch_depends": []
}
```

| 字段 | 说明 |
|------|------|
| `case_no` | 用例编号（从 1 开始） |
| `points` | 该测试点分值 |
| `time_limit_ms` / `memory_limit_kb` | 可覆盖题目默认限制（null 表示用题目配置） |
| `input_file` / `output_file` | 文件路径方式提供测试数据（如 S3/OSS 路径） |
| `input_inline` / `output_inline` | 内联文本方式提供测试数据（适用于小数据） |
| `input_sha256` / `output_sha256` | 文件哈希校验 |
| `batch_no` | IOI 批次号（null 表示非批次模式） |
| `batch_depends` | IOI 依赖的批次号列表 |

### 三种判题模式的消息差异

#### 1. STANDARD 模式

无额外字段。`judge_mode="STANDARD"`，不需要 `spj` 和 `interactor`。

判题逻辑（`modes/standard.py`）：
1. 编译用户程序 → 编译失败返回 CE
2. 并行运行所有测试用例
3. 逐用例比对输出（`checker.py`：去除末尾空白后的字符串比对）
4. 计分策略：
   - **ACM 模式**（`partial=false` 且无 batch）：首错即停，后面用例标记 SKIPPED
   - **OI 模式**（`partial=true`）：逐点累加 AC 用例的分数
   - **IOI 模式**（有 `batch_no`）：`aggregate_batches()` 批次聚合计分

#### 2. SPECIAL_JUDGE 模式

额外字段：

```json
{
  "judge_mode": "SPECIAL_JUDGE",
  "spj": {
    "language": {
      "key": "cpp17",
      "name": "C++17",
      "extension": ".cpp",
      "compile_command": "g++ -O2 -std=c++17 {src} -o {exe}",
      "run_command": "{exe}"
    },
    "source": "<SPJ checker 源代码>"
  }
}
```

判题逻辑（`modes/spj.py`）：
1. 编译用户程序 + 编译 checker（checker 编译一次，per-case 复用）
2. 逐用例：运行用户程序 → 运行 checker（传入 input / actual_output / expected_output）
3. Checker 判定逻辑判定 AC/WA

#### 3. INTERACTIVE 模式

额外字段：

```json
{
  "judge_mode": "INTERACTIVE",
  "interactor": {
    "language": {
      "key": "cpp17",
      "name": "C++17",
      "extension": ".cpp",
      "compile_command": "...",
      "run_command": "{exe}"
    },
    "source": "<交互器源代码>",
    "time_limit_ms": 4000,
    "memory_limit_kb": 262144
  }
}
```

判题逻辑（`modes/interactive.py`）：
1. 编译用户程序 + 编译交互器
2. 创建 FIFO 管道（user ↔ interactor 双向通信）
3. 并发运行用户程序和交互器，通过管道互联
4. 判定优先级：用户 runtime 错误 > 交互器 runtime 错误 > WA > AC
5. 交互器通过 stderr 输出 judge message，exit code 0=AC, 1=WA

---

## 二、MQ 返回结果（Worker → API）

### RabbitMQ 拓扑

| 项目 | 值 |
|------|-----|
| Exchange | `oj.judge`（复用同一个 exchange） |
| Queue | `oj.judge.result` |
| Routing Key | `result` |
| Content-Type | `application/json` |

### 消费者

`judge_result_consumer.py` 在模块启动时启动 `MQConsumerWorker("judge-result")`：
- 声明 exchange + queue + binding
- `prefetch_count=1`（逐个消费）
- `auto_ack=False`（手动 ACK）

### Payload 结构

对应 worker 侧 `JudgeResultOut`（`schemas.py`），由 `to_mq_dict()` 序列化。

#### 正常完成

```json
{
  "submission_id": "<snowflake-id>",
  "status": "COMPLETED",
  "result": "AC",
  "score": 100.0,
  "time_ms": 42,
  "memory_kb": 4096,
  "compile_output": "...",
  "compile_error": false,
  "cases": [
    {
      "case_no": 1,
      "result": "AC",
      "time_ms": 10,
      "memory_kb": 2048,
      "points": 33.33,
      "stdout_preview": "3\n",
      "stderr_preview": ""
    }
  ],
  "error": null,
  "wall_time_ms": 500
}
```

#### 执行失败

```json
{
  "submission_id": "<snowflake-id>",
  "status": "FAILED",
  "result": null,
  "score": 0.0,
  "time_ms": 0,
  "memory_kb": 0,
  "compile_output": null,
  "compile_error": false,
  "cases": [],
  "error": "具体错误信息",
  "wall_time_ms": 100
}
```

### 字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| `submission_id` | string | 对应的提交 ID |
| `status` | string | `COMPLETED`（正常完成）或 `FAILED`（执行异常） |
| `result` | string\|null | 最终判题结果，枚举值见下方 |
| `score` | float | 总得分 |
| `time_ms` | int | 总 CPU 时间（毫秒） |
| `memory_kb` | int | 峰值内存（KB） |
| `compile_output` | string\|null | 编译输出信息 |
| `compile_error` | bool | 是否为编译错误 |
| `cases[].case_no` | int | 用例编号 |
| `cases[].result` | string | 该用例判题结果 |
| `cases[].time_ms` | int | 该用例 CPU 时间 |
| `cases[].memory_kb` | int | 该用例内存占用 |
| `cases[].points` | float | 该用例得分 |
| `cases[].stdout_preview` | string | 用户输出截断预览（前 2048 字符） |
| `cases[].stderr_preview` | string | 标准错误输出预览（前 4096 字符） |
| `error` | string\|null | 错误信息（status=FAILED 时有值） |
| `wall_time_ms` | int | 墙钟时间（毫秒，包含编排开销） |

### 判题结果枚举 (`OjJudgeResult`)

| 值 | 含义 | 触发条件 |
|----|------|---------|
| `AC` | Accepted | 全部测试通过 |
| `WA` | Wrong Answer | 输出不匹配 / SPJ checker 判定错误 |
| `TLE` | Time Limit Exceeded | 超出 CPU 时间限制 |
| `MLE` | Memory Limit Exceeded | 超出内存限制 |
| `OLE` | Output Limit Exceeded | 输出超出长度限制 |
| `RE` | Runtime Error | 运行时错误（信号/非零退出） |
| `CE` | Compilation Error | 编译失败 |
| `PE` | Presentation Error | 格式错误（当前未使用） |
| `IE` | Internal Error | 内部错误 |
| `SE` | System Error | 系统错误 |
| `SKIPPED` | 跳过 | ACM 首错后跳过 / IOI 依赖失败跳过 |
| `PARTIAL` | 部分正确 | 部分得分（当前未使用） |

### 提交状态枚举 (`OjSubmitStatus`)

| 值 | 含义 |
|----|------|
| `QUEUED` | 等待排队 |
| `DISPATCHED` | 已分发 |
| `RUNNING` | 运行中 |
| `JUDGING` | 判题中 |
| `COMPLETED` | 已完成 |
| `FAILED` | 执行失败 |
| `CANCELLED` | 已取消 |

### 结果流转：消费者写入数据库

`judge_result_consumer.py::_handle_judge_result()` 将消息反序列化后写入：

```
OjSubmission 更新字段:
  status   = payload["status"]
  result   = payload["result"]
  score    = payload["score"]
  time_ms  = payload["time_ms"]
  memory_kb = payload["memory_kb"]
  compile_output = payload["compile_output"]
  judged_at = datetime.now(timezone.utc)
  case_points = payload["score"]
  case_total  = sum of cases[].total
  current_case = len(cases)

OjSubmissionCase 逐条创建:
  id, submission_id, case_no, status="COMPLETED"
  result, time_ms, memory_kb, points, total
  output = case_data["stdout_preview"]
  stderr = case_data["stderr_preview"]
  sort = case_no
```

---

## 三、完整消息流示例

### STANDARD 模式请求

```json
{
  "submission_id": "1234567890123456789",
  "judge_mode": "STANDARD",
  "problem": {"code": "A001", "time_limit_ms": 2000, "memory_limit_kb": 262144, "points": 100.0, "partial": false},
  "language": {"key": "cpp17", "name": "C++17", "extension": ".cpp", "compile_command": "g++ -O2 -std=c++17 {src} -o {exe}", "run_command": "{exe}"},
  "source": "#include <iostream>\nint main() { int a,b; std::cin>>a>>b; std::cout<<a+b; return 0; }",
  "test_cases": [
    {"case_no": 1, "points": 50.0, "time_limit_ms": null, "memory_limit_kb": null, "input_inline": "1 2\n", "output_inline": "3\n", "input_file": null, "output_file": null, "batch_no": null, "batch_depends": []},
    {"case_no": 2, "points": 50.0, "time_limit_ms": null, "memory_limit_kb": null, "input_inline": "10 20\n", "output_inline": "30\n", "input_file": null, "output_file": null, "batch_no": null, "batch_depends": []}
  ]
}
```

### 结果

```json
{
  "submission_id": "1234567890123456789",
  "status": "COMPLETED",
  "result": "AC",
  "score": 100.0,
  "time_ms": 15,
  "memory_kb": 3072,
  "compile_output": null,
  "compile_error": false,
  "cases": [
    {"case_no": 1, "result": "AC", "time_ms": 7, "memory_kb": 2048, "points": 50.0, "stdout_preview": "3", "stderr_preview": ""},
    {"case_no": 2, "result": "AC", "time_ms": 8, "memory_kb": 3072, "points": 50.0, "stdout_preview": "30", "stderr_preview": ""}
  ],
  "error": null,
  "wall_time_ms": 120
}
```

---

## 四、当前实现状态

Worker 端 `tasks.py` 的注释说明：**"结果通过 Celery 返回值传递（无 pika 发布到 MQ）"**。

即当前实现通过 Celery 的 return value + Redis result backend 回传结果，而非直接 publish 到 RabbitMQ。`JudgeResultOut.to_mq_dict()` 方法作为备用序列化器存在，`judge_result_consumer.py` 也准备就绪（由 `MQ__ENABLED` 控制），架构预留了"Worker 直接 publish 结果到 RabbitMQ"的能力。

## 五、关键文件索引

| 文件 | 内容 |
|------|------|
| `acoj/app/modules/oj/submission/submission/service_portal.py` | 构建 JudgeRequest dict 并 publish 到 RabbitMQ |
| `acoj/app/modules/oj/submission/submission/judge_result_consumer.py` | MQ 消费者：解析结果 JSON 写入 DB |
| `acoj/app/platform/mq/producer.py` | `EventProducer` - JSON 编码 + publish |
| `acoj/app/platform/mq/message.py` | `MQMessage` dataclass - 封装 pika 消息 |
| `acoj/app/platform/mq/consumer.py` | `MQConsumerWorker` - 可复用阻塞消费者 |
| `acoj-worker/app/modules/judge/schemas.py` | Pydantic 模型：`JudgePayload`、`JudgeResultOut`、`CaseResult` |
| `acoj-worker/app/modules/judge/tasks.py` | Celery task `judge.execute` - 接收 payload，返回 result dict |
| `acoj-worker/app/modules/judge/orchestrator.py` | 编排层：按 judge_mode 派发策略 |
| `acoj-worker/app/modules/judge/modes/standard.py` | STANDARD 模式实现（ACM/OI/IOI） |
| `acoj-worker/app/modules/judge/modes/spj.py` | SPECIAL_JUDGE 模式实现 |
| `acoj-worker/app/modules/judge/modes/interactive.py` | INTERACTIVE 模式实现 |
| `acoj-worker/app/modules/judge/result_mapper.py` | Sandbox Status → OJ Result 映射 |
| `acoj-worker/app/modules/judge/scoring.py` | IOI 批次聚合 + 错误结果构造 |
| `acoj-worker/app/modules/judge/checker.py` | 输出比对（去末尾空白） |
| `acoj/app/modules/oj/enums.py` | 所有枚举定义（`OjJudgeResult`、`OjJudgeMode`、`OjSubmitStatus` 等） |
| `acoj/app/core/config/settings.py` | 配置：`CelerySettings`、`MQSettings` |
