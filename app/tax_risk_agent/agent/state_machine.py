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

from enum import Enum

class AgentState(str, Enum):
    THINK = "think"
    EVALUATE_EVIDENCE = "evaluate_evidence"    # 评估证据,
    ACT = "act"   
    OBSERVE = "observe"
    RESOLVE_CONFLICT = "resolve_conflict"  # 解决冲突
    CHECK_BUDGET = "check_budget"    # 检查预算
    CONCLUDE = "conclude"            # conclude  推断
    HUMAN_REVIEW = "human_review"