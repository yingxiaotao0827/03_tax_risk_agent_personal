from app.tax_risk_agent.models.domain import Evidence


class RuleRetrievalTool:
    """税务规则检索工具。"""

    def __init__(self, rule_store):
        self.rule_store = rule_store

    def search(self, query: str, limit: int = 3) -> list[Evidence]:
        rules = self.rule_store.search(query, limit=limit)
        return [
            Evidence(
                source="rule_store",
                summary=f"{rule.title}: {rule.content}",
                data={"rule_id": rule.rule_id, "tags": list(rule.tags)},
                confidence=0.75,
            )
            for rule in rules
        ]
