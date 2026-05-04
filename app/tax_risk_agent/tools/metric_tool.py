# 财务指标计算工具

from decimal import Decimal,ROUND_HALF_UP

def _round(value:float) -> float:
  return float(
    Decimal(str(value)).quantize(
      Decimal('0.0001'), 
      rounding=ROUND_HALF_UP
    )
  )

class MetricTool:
  def calculate(self, financial:dict) -> dict[str,float]:
    revenue = financial['revenue'] or 1.0
    cost = financial['cost']
    vat_paid = financial['vat_paid']
    travel_expense = financial['travel_expense']
    consulting_expense = financial['consulting_expense']
    employee_count = financial['employee_count']

    gross_margin = (revenue - cost) / revenue
    vat_burden_rate = vat_paid / revenue
    travel_expense_rate = travel_expense / revenue
    consulting_expense_ratio = consulting_expense / revenue
    travel_per_employee = travel_expense / employee_count

    return {
      'gross_margin': _round(gross_margin),
      'vat_burden_rate': _round(vat_burden_rate),
      'travel_expense_rate': _round(travel_expense_rate),
      'consulting_expense_ratio': _round(consulting_expense_ratio),
      'travel_per_employee': _round(travel_per_employee)
    }