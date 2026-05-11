"""税务风险诊断智能体模块

本模块负责组织企业税务健康诊断的完整执行流程：读取企业期间财务与发票数据，
调用指标计算、规则检索、SQL 查询、交叉验证、图表渲染和报告生成等组件，
将风险场景评估结果汇总为结构化的 `DiagnosticResult`。

核心类 `TaxRiskDiagnosticAgent` 是应用层编排入口；`RiskScenario` 描述单个
可自动化评估的风险场景；模块内的默认场景覆盖差旅费异常、增值税税负率偏低
和咨询服务费集中复核等演示风险。
"""

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from app.tax_risk_agent.agent.state_machine import AgentRunState, AgentState
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


def vat_gross_margin_cross_check(metrics: dict, benchmarks: dict) -> Evidence | None:
    """使用毛利率基准对增值税税负率偏低场景进行交叉验证。"""
    # 流程 1：先从已计算指标和行业基准中取出交叉验证所需的毛利率数据。
    gross_margin_p50 = benchmarks.get("gross_margin", {}).get("p50")
    gross_margin = metrics.get("gross_margin")

    # 流程 2：如果任一数据缺失，不能完成自动验证，只返回低置信度证据供人工参考。
    if gross_margin is None or gross_margin_p50 is None:
        return Evidence(
            source="benchmark_cross_check",
            summary="缺少毛利率或行业毛利率基准，税负率偏低无法完成交叉验证。",
            data={"gross_margin": gross_margin, "gross_margin_p50": gross_margin_p50},
            confidence=0.45,
        )

    # 流程 3：毛利率不低但增值税税负率偏低时，形成支持风险判断的交叉证据。
    if gross_margin >= gross_margin_p50:
        return Evidence(
            source="benchmark_cross_check",
            summary=f"毛利率 {gross_margin:.2%} 不低于行业 P50 {gross_margin_p50:.2%}，但税负率偏低，存在进项抵扣或收入确认异常信号。",
            data={"gross_margin": gross_margin, "gross_margin_p50": gross_margin_p50},
            confidence=0.78,
        )

    # 流程 4：毛利率同步偏低时，交叉验证不支持风险升级，返回 None 让主流程跳过该风险。
    return None


DEFAULT_RISK_SCENARIOS = [
    RiskScenario(
        code="TRAVEL_RATIO",
        title="差旅费异常占比风险",
        metric="travel_expense_ratio",
        benchmark_metric="travel_expense_ratio",
        benchmark_field="p90",
        operator=">",
        level=RiskLevel.high,
        rule_query="travel expense invoice",
        invoice_category="travel",
        conclusion_template="{metric_label} {metric_value:.2%} 高于行业 {benchmark_field_upper} {benchmark_value:.2%}，且存在进一步核验空间，可能涉及费用真实性或税前扣除合规风险。",
        suggestions=["补充差旅审批、行程记录、合同和付款流水。", "抽样核验高金额差旅发票对应的真实业务场景。"],
    ),
    RiskScenario(
        code="VAT_BURDEN",
        title="增值税税负率偏低风险",
        metric="vat_burden_rate",
        benchmark_metric="vat_burden_rate",
        benchmark_field="p50",
        operator="<",
        level=RiskLevel.medium,
        rule_query="vat burden revenue invoice",
        cross_check=vat_gross_margin_cross_check,
        conclusion_template="{metric_label} {metric_value:.2%} 低于行业 {benchmark_field_upper} {benchmark_value:.2%}，且毛利率未同步偏低，需要关注进项抵扣和收入确认口径。",
        suggestions=["复核进项发票抵扣链路。", "按客户和月份拆分收入确认节奏。", "检查是否存在异常进项抵扣或收入递延确认。"],
    ),
    RiskScenario(
        code="CONSULTING_CLUSTER",
        title="咨询服务费集中复核风险",
        metric="consulting_expense_ratio",
        benchmark_metric="consulting_expense_ratio",
        benchmark_field="p75",
        operator=">",
        level=RiskLevel.review_required,
        rule_query="consulting counterparty invoice",
        invoice_category="consulting",
        conclusion_template="咨询费率 {metric_value:.2%} 暂缺可比行业基准或交付材料证据，不能自动认定风险，需要人工复核真实性。",
        suggestions=["补充咨询合同、项目验收单、咨询报告和付款流水。", "核验咨询服务商经营能力及是否存在关联关系。"],
    ),
]

METRIC_LABELS = {
    "travel_expense_ratio": "差旅费率",
    "vat_burden_rate": "增值税税负率",
    "gross_margin": "毛利率",
    "consulting_expense_ratio": "咨询费率",
    "travel_per_employee": "人均差旅费",
}


class TaxRiskDiagnosticAgent:
    """按 ReAct 状态机执行一次税务风险诊断。"""

    def __init__(
        self,
        database: TaxRiskDatabase,
        rule_tool: RuleRetrievalTool,
        report_generator: ReportGenerator,
        chart_dir: Path,
        llm_client: LLMClient | None = None,
        scenarios: list[RiskScenario] | None = None,
        max_tool_rounds: int = 8,
    ):
        self.database = database
        self.sql_tool = SafeSqlTool(database)
        self.metric_tool = MetricTool()
        self.rule_tool = rule_tool
        self.report_generator = report_generator
        self.chart_dir = chart_dir
        self.llm_client = llm_client or OfflineLLMClient()
        self.scenarios = scenarios or DEFAULT_RISK_SCENARIOS
        self.max_tool_rounds = max_tool_rounds

    def run(self, request: DiagnosticRequest) -> DiagnosticResult:
        """执行完整诊断，并返回最终状态快照。"""
        state = AgentRunState(
            company_id=request.company_id,
            period=request.period,
            max_tool_rounds=self.max_tool_rounds,
        )

        state.record(f"开始诊断 {request.company_id} / {request.period}，加载 {len(self.scenarios)} 个风险场景。")
        state.transition_to(AgentState.ACT, "需要读取财务数据、行业基准并计算指标")

        state.financial = self._load_financial(state)
        if state.financial is None:
            state.needs_human_review = True
            state.transition_to(AgentState.HUMAN_REVIEW, "未找到财务报表数据，无法自动诊断")
            return self._build_result(state)

        state.benchmarks = self._load_benchmarks(state)
        self._consume_tool_round(state, "metric_tool.calculate")
        state.metrics = self.metric_tool.calculate(state.financial)
        state.record(f"完成指标计算：{state.metrics}")

        state.transition_to(AgentState.OBSERVE, "工具结果已返回，准备形成证据")
        state.evidence.append(
            Evidence(
                source="financial_statements",
                summary="已读取企业期间财务报表并计算关键税务指标。",
                data={"financial": state.financial, "metrics": state.metrics},
                confidence=0.8,
            )
        )

        state.transition_to(AgentState.EVALUATE_EVIDENCE, "逐个风险场景评估证据充分性")
        for scenario in self.scenarios:
            if state.current_state == AgentState.HUMAN_REVIEW:
                break
            finding = self._evaluate_scenario(state, scenario)
            if finding is not None:
                state.findings.append(finding)
                state.record(f"形成风险发现：{finding.code} / {finding.level.value}")

        state.transition_to(AgentState.RESOLVE_CONFLICT, "交叉验证已在场景评估中完成")
        state.needs_human_review = state.needs_human_review or any(
            finding.level == RiskLevel.review_required for finding in state.findings
        )

        state.transition_to(AgentState.CHECK_BUDGET, "检查工具调用轮次")
        if state.tool_rounds > state.max_tool_rounds:
            state.needs_human_review = True
            state.transition_to(AgentState.HUMAN_REVIEW, "工具调用轮次超过预算，需要人工复核")
        else:
            state.record(f"工具调用轮次 {state.tool_rounds}/{state.max_tool_rounds}，未超过预算。")
            state.transition_to(AgentState.CONCLUDE, "证据评估完成，生成最终结论")

        chart_path = render_metric_chart(state.metrics, state.benchmarks, self.chart_dir)
        if chart_path is not None:
            state.chart_paths.append(chart_path)

        return self._build_result(state)

    def _load_financial(self, state: AgentRunState) -> dict | None:
        self._consume_tool_round(state, "sql_tool.financial_statements")
        rows = self.sql_tool.run(
            "SELECT * FROM financial_statements WHERE company_id = ? AND period = ?",
            (state.company_id, state.period),
        )
        state.record(f"读取财务报表 {len(rows)} 行。")
        return rows[0] if rows else None

    def _load_benchmarks(self, state: AgentRunState) -> dict[str, dict]:
        self._consume_tool_round(state, "sql_tool.industry_benchmarks")
        rows = self.sql_tool.run(
            "SELECT metric, p50, p75, p90 FROM industry_benchmarks WHERE period = ?",
            (state.period,),
        )
        benchmarks = {row["metric"]: {"p50": row["p50"], "p75": row["p75"], "p90": row["p90"]} for row in rows}
        state.record(f"读取行业基准 {len(benchmarks)} 项。")
        return benchmarks

    def _evaluate_scenario(self, state: AgentRunState, scenario: RiskScenario) -> RiskFinding | None:
        metric_value = state.metrics.get(scenario.metric)
        benchmark_value = state.benchmarks.get(scenario.benchmark_metric, {}).get(scenario.benchmark_field)
        metric_label = METRIC_LABELS.get(scenario.metric, scenario.metric)

        if metric_value is None:
            state.record(f"{scenario.code} 缺少指标 {scenario.metric}，跳过自动判断。")
            return None

        if benchmark_value is None and scenario.level != RiskLevel.review_required:
            state.record(f"{scenario.code} 缺少行业基准 {scenario.benchmark_metric}.{scenario.benchmark_field}，跳过自动判断。")
            return None

        if benchmark_value is not None and not self._matches(metric_value, benchmark_value, scenario.operator):
            state.record(f"{scenario.code} 未触发：{metric_label}={metric_value:.2%}，基准={benchmark_value:.2%}。")
            return None

        evidence = [
            Evidence(
                source="metric_tool",
                summary=self._metric_summary(metric_label, metric_value, scenario, benchmark_value),
                data={
                    "metric": scenario.metric,
                    "metric_value": metric_value,
                    "benchmark_metric": scenario.benchmark_metric,
                    "benchmark_field": scenario.benchmark_field,
                    "benchmark_value": benchmark_value,
                },
                confidence=0.82 if benchmark_value is not None else 0.55,
            )
        ]

        evidence.extend(self._retrieve_rule_evidence(state, scenario))

        invoice_evidence = self._build_invoice_evidence(state, scenario)
        if invoice_evidence is not None:
            evidence.append(invoice_evidence)

        if scenario.cross_check is not None:
            cross_check = scenario.cross_check(state.metrics, state.benchmarks)
            if cross_check is None:
                state.record(f"{scenario.code} 交叉验证不支持风险升级，跳过结论。")
                return None
            evidence.append(cross_check)

        if scenario.level == RiskLevel.review_required:
            state.needs_human_review = True

        return RiskFinding(
            code=scenario.code,
            title=scenario.title,
            level=scenario.level,
            conclusion=scenario.conclusion_template.format(
                metric_label=metric_label,
                metric_value=metric_value,
                benchmark_field_upper=scenario.benchmark_field.upper(),
                benchmark_value=benchmark_value or 0.0,
            ),
            evidence=evidence,
            suggestions=scenario.suggestions,
        )

    def _retrieve_rule_evidence(self, state: AgentRunState, scenario: RiskScenario) -> list[Evidence]:
        self._consume_tool_round(state, f"rule_tool.search.{scenario.code}")
        evidence = self.rule_tool.search(scenario.rule_query, limit=2)
        state.record(f"{scenario.code} 召回税务规则 {len(evidence)} 条。")
        return evidence

    def _build_invoice_evidence(self, state: AgentRunState, scenario: RiskScenario) -> Evidence | None:
        if scenario.invoice_category is None:
            return None

        self._consume_tool_round(state, f"sql_tool.invoices.{scenario.invoice_category}")
        rows = self.sql_tool.run(
            """
            SELECT counterparty, COUNT(*) AS invoice_count, SUM(amount) AS total_amount, SUM(tax_amount) AS total_tax
            FROM invoices
            WHERE company_id = ? AND period = ? AND category = ?
            GROUP BY counterparty
            ORDER BY total_amount DESC
            """,
            (state.company_id, state.period, scenario.invoice_category),
        )
        if not rows:
            return Evidence(
                source="invoices",
                summary=f"未查询到 {scenario.invoice_category} 类发票，证据不足。",
                data={"category": scenario.invoice_category},
                confidence=0.4,
            )

        top = rows[0]
        return Evidence(
            source="invoices",
            summary=f"{scenario.invoice_category} 类发票最大对手方为 {top['counterparty']}，金额合计 {top['total_amount']:.2f}。",
            data={"category": scenario.invoice_category, "counterparties": rows},
            confidence=0.72,
        )

    def _build_result(self, state: AgentRunState) -> DiagnosticResult:
        result = DiagnosticResult(
            company_id=state.company_id,
            period=state.period,
            executive_summary=self.llm_client.summarize_findings(state.findings),
            findings=state.findings,
            reasoning_trace=state.reasoning_trace,
            chart_paths=state.chart_paths,
            needs_human_review=state.needs_human_review,
        )
        result.report_path = self.report_generator.render(result)
        return result

    def _consume_tool_round(self, state: AgentRunState, tool_name: str) -> None:
        state.tool_rounds += 1
        state.record(f"调用工具 {tool_name}，当前轮次 {state.tool_rounds}/{state.max_tool_rounds}。")
        if state.tool_rounds > state.max_tool_rounds:
            state.needs_human_review = True
            state.current_state = AgentState.HUMAN_REVIEW

    @staticmethod
    def _matches(metric_value: float, benchmark_value: float, operator: str) -> bool:
        if operator == ">":
            return metric_value > benchmark_value
        if operator == "<":
            return metric_value < benchmark_value
        if operator == ">=":
            return metric_value >= benchmark_value
        if operator == "<=":
            return metric_value <= benchmark_value
        if operator == "==":
            return metric_value == benchmark_value
        raise ValueError(f"Unsupported scenario operator: {operator}")

    @staticmethod
    def _metric_summary(
        metric_label: str,
        metric_value: float,
        scenario: RiskScenario,
        benchmark_value: float | None,
    ) -> str:
        if benchmark_value is None:
            return f"{metric_label} 为 {metric_value:.2%}，但缺少行业 {scenario.benchmark_field.upper()} 基准，需要人工复核。"
        return f"{metric_label} 为 {metric_value:.2%}，行业 {scenario.benchmark_field.upper()} 基准为 {benchmark_value:.2%}。"
