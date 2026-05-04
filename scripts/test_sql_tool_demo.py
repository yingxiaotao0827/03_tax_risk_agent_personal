# 测试 SafeSqlTool
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.tax_risk_agent.data.database import TaxRiskDatabase
from app.tax_risk_agent.tools.sql_tool import SafeSqlTool


db = TaxRiskDatabase(Path("data/tax_risk_demo.sqlite"))
tool = SafeSqlTool(db)

rows = tool.run(
    "SELECT * FROM financial_statements WHERE company_id = ? AND period = ?",
    ("demo_co", "2025Q2"),
)

print(rows)

# tool.run("DELETE FROM financial_statements")  # 测试危险 SQL
