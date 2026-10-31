"""智能体包：data_agent / marketing_agent / fulfillment_agent。

各 agent 以独立模块 + 清晰函数边界实现，体现"隔离会话"的设计意图：
即便 MVP 为进程内函数，也通过模块边界表达不同 agent 的职责与隔离。
"""
