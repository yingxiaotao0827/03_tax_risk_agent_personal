# 测试 MetricTool 财务指标计算工具
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.tax_risk_agent.tools.metric_tool import MetricTool


financial = {
    "revenue": 12_000_000,
    "cost": 8_400_000,
    "vat_paid": 360_000,
    "travel_expense": 980_000,
    "consulting_expense": 1_250_000,
    "employee_count": 82,
}

metrics = MetricTool().calculate(financial)
print(metrics)
