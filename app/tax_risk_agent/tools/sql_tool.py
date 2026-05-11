#  只读 SQL 查询工具
from app.tax_risk_agent.data.database import TaxRiskDatabase

class SafeSqlTool:
  def __init__(self, database:TaxRiskDatabase):
    self.database = database

  def run(self, sql:str,params:tuple = ()) -> list[dict]:
    normalized = sql.strip().lower()  # 把 SQL 去掉前后空格并转成小写，方便检查。

    if not normalized.startswith("select"): # 只允许 SELECT 开头
      raise ValueError("只允许 SELECT 查询") 

    # 定义危险关键词
    blocked_tokens = (
      ";",
      "drop",
      "delete",
      "update",
      "insert",
      "alter",
      "attach",
      "detach",
      "pragma",
      "vacuum",
    )

    wrapped_sql = f" {normalized} " # 给 SQL 前后加空格，方便检查关键词;可以避免误伤普通单词
    if any(token in wrapped_sql for token in blocked_tokens):# 如果在危险关键词列表中发现任何一个，就抛出异常
      raise ValueError("不允许 SQL query")
    
    return self.database.query(sql, params) # 通过数据库访问类执行查询，并返回结果