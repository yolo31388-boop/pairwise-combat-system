"""
pairwise-combat-system - CombatSystem

This module contains a deliberately broken implementation.
Fix all bugs so that tests pass.
"""


class CombatSystem:
    def __init__(self):
        self.state = {}

    def calculate_damage(self, *args, **kwargs):
        """BUG: 伤害计算不检查目标状态，无敌和闪避目标也受伤"""
        return None

    def check_hit(self, *args, **kwargs):
        """BUG: 命中判定只看命中率，不看目标闪避和等级差"""
        return None

    def apply_status_effect(self, *args, **kwargs):
        """BUG: 状态效果不做持续时间，上了就永远存在"""
        return None

    def calculate_aoe(self, *args, **kwargs):
        """BUG: AOE范围用矩形判定，不是圆形"""
        return None

    def log_combat_event(self, *args, **kwargs):
        """BUG: 战斗日志只记录伤害数字，不记录技能和状态"""
        return None

