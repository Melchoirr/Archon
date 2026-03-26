"""所有枚举类型定义"""

from enum import StrEnum


class PhaseState(StrEnum):
    """阶段/迭代状态"""
    pending = "pending"
    in_progress = "in_progress"
    running = "running"
    completed = "completed"
    failed = "failed"
    skipped = "skipped"


class IdeaStatus(StrEnum):
    """Idea 生命周期状态"""
    proposed = "proposed"
    recommended = "recommended"
    deprioritized = "deprioritized"
    active = "active"
    completed = "completed"
    failed = "failed"


class IdeaCategory(StrEnum):
    """Idea 类别"""
    loss = "loss"
    architecture = "architecture"
    training = "training"
    inference = "inference"
    theory = "theory"


class ExperienceType(StrEnum):
    """经验日志类型"""
    insight = "insight"
    success = "success"
    failure = "failure"
    observation = "observation"


class RelationType(StrEnum):
    """Idea 间关系类型"""
    builds_on = "builds_on"
    alternative_to = "alternative_to"
    complementary = "complementary"
    combines_with = "combines_with"
