from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class RiskLevel(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"
    review_required = "review_required"

# Evidence：证据，比如指标、SQL 查询结果、规则内容
class Evidence(BaseModel):  
    source: str
    summary: str
    data: dict[str, Any] = Field(default_factory=dict)
    confidence: float = 0.7

# RiskFinding：风险结论
class RiskFinding(BaseModel):
    code: str
    title: str
    level: RiskLevel
    conclusion: str
    evidence: list[Evidence]
    suggestions: list[str]

# DiagnosticRequest：用户输入
class DiagnosticRequest(BaseModel):
    company_id: str
    period: str
    max_rounds: int = 6

# DiagnosticResult：Agent 输出结果
class DiagnosticResult(BaseModel):
    company_id: str
    period: str
    findings: list[RiskFinding]
    reasoning_trace: list[str]
    report_path: Path | None = None
    needs_human_review: bool = False
