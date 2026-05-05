"""税务风险诊断智能体模块「

本模块负责组织企业税务健康诊断的完整执行流程:读取企业期间财务与发票数据
调用指标计算、规则检索、SQL 查询、交叉验证、图表渲染和报告生成等组件，
将风险场景评估结果汇总为结构化的 `DiagnosticResult`。

核心类 `TaxRiskDiagnosticAgent` 是应用层编排入口；`RiskScenario` 描述单个
可自动化评估的风险场景；模块内的默认场景覆盖差旅费异常、增值税税负率偏低
和咨询服务费集中复核等演示风险。
"""

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from app.tax_risk_agent.agent.state_machine import AgentState
from app.tax_risk_agent.core.llm_client import LLMClient, OfflineLLMClient
from app.tax_risk_agent.data.database import TaxRiskDatabase
from app.tax_risk_agent.models.domain import DiagnosticRequest, DiagnosticResult, Evidence, RiskFinding, RiskLevel
from app.tax_risk_agent.reports.charting import render_metric_chart
from app.tax_risk_agent.reports.report_generator import ReportGenerator
from app.tax_risk_agent.tools.metric_tool import MetricTool
from app.tax_risk_agent.tools.rule_tool import RuleRetrievalTool
from app.tax_risk_agent.tools.sql_tool import SafeSqlTool


@dataclass(frozen=True)
class RiskScenario:
    code: str
    title: str
    metric: str
    benchmark_metric: str
    benchmark_field: str
    operator: str
    level: RiskLevel
    rule_query: str
    conclusion_template: str
    suggestions: list[str]
    invoice_category: str | None = None
    cross_check: Callable[[dict, dict], Evidence | None] | None = None

    