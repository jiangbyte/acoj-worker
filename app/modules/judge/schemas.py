"""Judge 模块输入/输出 Pydantic 模型。"""

from pydantic import BaseModel, Field


class ProblemConfig(BaseModel):
    """题目配置。"""
    code: str
    time_limit_ms: int
    memory_limit_kb: int
    points: float = 100.0
    partial: bool = False


class LanguageConfigIn(BaseModel):
    """语言配置（来自判题请求）。"""
    key: str
    name: str = ""
    extension: str = ""
    compile_command: str | None = None
    run_command: str | None = None


class TestCaseData(BaseModel):
    """单个测试点数据。"""
    case_no: int
    points: float = 0.0
    time_limit_ms: int | None = None
    memory_limit_kb: int | None = None
    input_inline: str = ""
    output_inline: str | None = None
    input_file: str | None = None
    output_file: str | None = None
    input_sha256: str = ""
    output_sha256: str = ""
    batch_no: int | None = None
    batch_depends: list[int] = Field(default_factory=list)


class JudgePayload(BaseModel):
    """判题请求 payload（Celery task 输入）。"""
    submission_id: str
    judge_mode: str = "STANDARD"
    problem: ProblemConfig
    language: LanguageConfigIn | None = None
    source: str = ""
    test_cases: list[TestCaseData] = Field(default_factory=list)
    spj: dict | None = None
    interactor: dict | None = None


class CaseResult(BaseModel):
    """单个测试点判题结果。"""
    case_no: int
    result: str = "IE"
    time_ms: int = 0
    memory_kb: int = 0
    points: float = 0.0
    stdout_preview: str = ""
    stderr_preview: str = ""


class JudgeResultOut(BaseModel):
    """判题结果（Celery task 返回值）。"""
    submission_id: str
    status: str = "COMPLETED"
    result: str | None = None
    score: float = 0.0
    time_ms: int = 0
    memory_kb: int = 0
    compile_output: str | None = None
    compile_error: bool = False
    cases: list[CaseResult] = Field(default_factory=list)
    error: str | None = None
    wall_time_ms: int = 0

    def to_mq_dict(self) -> dict:
        """序列化为 MQ 兼容字典（与旧格式一致）。"""
        return self.model_dump()
