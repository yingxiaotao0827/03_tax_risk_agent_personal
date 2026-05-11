from app.tax_risk_agent.vectorstore.rules import DEFAULT_RULES, TaxRule


class InMemoryRuleStore:
    """本地演示用规则库，按标签和正文做简单召回。"""

    def __init__(self, rules: list[TaxRule] | None = None):
        self.rules = rules or DEFAULT_RULES

    def search(self, query: str, limit: int = 3) -> list[TaxRule]:
        terms = set(query.lower().split())

        def score(rule: TaxRule) -> int:
            haystack = " ".join((rule.rule_id, rule.title, rule.content, " ".join(rule.tags))).lower()
            return sum(1 for term in terms if term in haystack)

        ranked = sorted(self.rules, key=score, reverse=True)
        return [rule for rule in ranked if score(rule) > 0][:limit]


def build_rule_store(milvus_uri: str, collection: str) -> InMemoryRuleStore:
    """构建规则库。

    当前项目保留 Milvus 参数作为未来扩展点；本地实现使用内存规则库。
    """
    return InMemoryRuleStore()
