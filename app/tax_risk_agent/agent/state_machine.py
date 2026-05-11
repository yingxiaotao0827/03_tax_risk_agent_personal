"""
状态机
THINK               生成风险假设
EVALUATE_EVIDENCE   判断证据是否充分
ACT                 调用工具
OBSERVE             接收工具结果
RESOLVE_CONFLICT    做交叉验证
CHECK_BUDGET        检查轮次/工具调用预算
CONCLUDE            生成结论
HUMAN_REVIEW        转人工复核
"""

from dataclasses import dataclass, field
from enum import Enum

from app.tax_risk_agent.models.domain import Evidence, RiskFinding

class AgentState(str, Enum):
    THINK = "think" # 生成风险假设
    EVALUATE_EVIDENCE = "evaluate_evidence"    # 评估证据,判断证据是否充分
    ACT = "act"   # 调用工具，比如 SQL、指标计算、规则检索
    OBSERVE = "observe"
    RESOLVE_CONFLICT = "resolve_conflict"  # 做交叉验证/冲突消解
    CHECK_BUDGET = "check_budget"    # 检查轮次或工具调用预算
    CONCLUDE = "conclude"            # 生成结论
    HUMAN_REVIEW = "human_review"   # 转人工复核


@dataclass
class AgentRunState:
    """一次诊断运行期间的内存状态快照。"""

    company_id: str
    period: str
    current_state: AgentState = AgentState.THINK
    tool_rounds: int = 0
    max_tool_rounds: int = 8
    financial: dict | None = None
    metrics: dict[str, float] = field(default_factory=dict)
    benchmarks: dict[str, dict] = field(default_factory=dict)
    evidence: list[Evidence] = field(default_factory=list)
    findings: list[RiskFinding] = field(default_factory=list)
    reasoning_trace: list[str] = field(default_factory=list)
    chart_paths: list = field(default_factory=list)
    needs_human_review: bool = False

    def transition_to(self, next_state: AgentState, reason: str) -> None:
        self.reasoning_trace.append(f"{self.current_state.value} -> {next_state.value}: {reason}")
        self.current_state = next_state

    def record(self, message: str) -> None:
        self.reasoning_trace.append(f"{self.current_state.value}: {message}")
