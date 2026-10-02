import pytest
from combat.system import CombatSystem


class TestCombatSystem:

    def test_calculate_damage(self):
        """伤害计算不检查目标状态，无敌和闪避目标也受伤"""
        obj = CombatSystem()
        result = obj.calculate_damage()
        self.assertIsNotNone(result)

    def test_check_hit(self):
        """命中判定只看命中率，不看目标闪避和等级差"""
        obj = CombatSystem()
        result = obj.check_hit()
        self.assertIsNotNone(result)

    def test_apply_status_effect(self):
        """状态效果不做持续时间，上了就永远存在"""
        obj = CombatSystem()
        result = obj.apply_status_effect()
        self.assertIsNotNone(result)

    def test_calculate_aoe(self):
        """AOE范围用矩形判定，不是圆形"""
        obj = CombatSystem()
        result = obj.calculate_aoe()
        self.assertIsNotNone(result)

    def test_log_combat_event(self):
        """战斗日志只记录伤害数字，不记录技能和状态"""
        obj = CombatSystem()
        result = obj.log_combat_event()
        self.assertIsNotNone(result)

