"""
pairwise-combat-system - CombatSystem

Combat resolution system featuring:

- damage calculation with target-status checks, damage types and variance
- hit resolution with dodge, level difference, critical hits and blocks
- status effects with durations, stacking rules and dispel
- circular AoE with damage falloff and friendly-fire control
- structured combat log with filtering and replay
"""

from __future__ import annotations

import math
import random
import time

PHYSICAL = "physical"
MAGICAL = "magical"
DAMAGE_TYPES = (PHYSICAL, MAGICAL)

# Statuses that make a target immune to all damage.
IMMUNE_STATUSES = frozenset({"invincible", "invulnerable", "untargetable"})
# Statuses that make a target avoid any incoming hit.
EVADE_STATUSES = frozenset({"dodge", "evasion", "evading"})


def _status_names(target):
    names = set()
    for status in target.get("statuses", []) or []:
        if isinstance(status, str):
            names.add(status)
        elif isinstance(status, dict):
            names.add(status.get("type"))
    names.discard(None)
    return names


def _clamp(value, low, high):
    return max(low, min(high, value))


class CombatSystem:
    def __init__(self, seed=None):
        self.state = {}
        self.combat_log = []
        self._rng = random.Random(seed)

    # ------------------------------------------------------------------
    # Damage
    # ------------------------------------------------------------------
    def calculate_damage(self, attacker=None, target=None, skill=None,
                         damage_type=None, variance=0.1):
        """Return the final damage of an attack.

        Returns 0 when the target is invincible or currently evading.
        Physical damage is reduced by ``defense``, magical damage by
        ``magic_defense``. The result is varied by +/- ``variance``.
        """
        attacker = attacker or {}
        target = target or {}
        skill = skill or {}

        statuses = _status_names(target)
        if statuses & (IMMUNE_STATUSES | EVADE_STATUSES):
            return 0

        damage_type = damage_type or skill.get("damage_type") or PHYSICAL
        if damage_type not in DAMAGE_TYPES:
            raise ValueError(f"unknown damage type: {damage_type!r}")

        if damage_type == PHYSICAL:
            attack = attacker.get("attack", attacker.get("attack_power", 10))
            defense = target.get("defense", 0)
        else:
            attack = attacker.get(
                "magic_attack",
                attacker.get("spell_power", attacker.get("attack", 10)),
            )
            defense = target.get("magic_defense", target.get("resistance", 0))

        base = skill.get("base_damage", attack) * skill.get("multiplier", 1.0)
        raw = max(1.0, base - defense)

        spread = _clamp(float(variance), 0.0, 0.9)
        roll = 1.0 + self._rng.uniform(-spread, spread)
        return max(1, int(round(raw * roll)))

    # ------------------------------------------------------------------
    # Hit resolution
    # ------------------------------------------------------------------
    def check_hit(self, attacker=None, target=None, skill=None):
        """Resolve hit / crit / block.

        Hit chance accounts for attacker accuracy, target dodge and the
        level difference between them. Returns a dict with ``hit``,
        ``crit``, ``blocked`` and the final ``hit_chance``.
        """
        attacker = attacker or {}
        target = target or {}
        skill = skill or {}

        result = {"hit": False, "crit": False, "blocked": False,
                  "hit_chance": 0.0}

        if _status_names(target) & EVADE_STATUSES:
            return result

        accuracy = attacker.get("accuracy", skill.get("accuracy", 100))
        dodge = target.get("dodge", target.get("evasion", 0))
        level_diff = attacker.get("level", 1) - target.get("level", 1)
        level_mod = _clamp(level_diff * 2, -20, 20)

        hit_chance = _clamp(accuracy - dodge + level_mod, 5, 100)
        result["hit_chance"] = hit_chance
        if self._rng.uniform(0, 100) >= hit_chance:
            return result

        result["hit"] = True

        block_chance = target.get("block", target.get("block_rate", 0))
        if block_chance and self._rng.uniform(0, 100) < block_chance:
            result["blocked"] = True
            return result

        crit_chance = attacker.get("crit_rate", skill.get("crit_rate", 0))
        if crit_chance and self._rng.uniform(0, 100) < crit_chance:
            result["crit"] = True
        return result

    # ------------------------------------------------------------------
    # Status effects
    # ------------------------------------------------------------------
    def _resolve_target(self, target):
        if target is not None:
            return target
        return self.state.setdefault("default_target", {})

    def apply_status_effect(self, target=None, effect=None):
        """Apply a status effect with duration and stacking rules.

        Re-applying the same effect refreshes its duration and adds a
        stack, capped at ``max_stacks`` (default 1). Returns the active
        effect entry.
        """
        target = self._resolve_target(target)
        effect = dict(effect or {"type": "unknown", "duration": 3})
        effect.setdefault("duration", 3)
        max_stacks = max(1, effect.get("max_stacks", 1))

        effects = target.setdefault("status_effects", [])
        for existing in effects:
            if existing["type"] == effect["type"]:
                existing["remaining"] = max(existing["remaining"],
                                            effect["duration"])
                existing["stacks"] = min(existing.get("stacks", 1) + 1,
                                         max_stacks)
                entry = existing
                break
        else:
            effect["remaining"] = effect["duration"]
            effect["stacks"] = 1
            effects.append(effect)
            entry = effect

        target["statuses"] = [e["type"] for e in effects]
        return entry

    def tick_status_effects(self, target=None):
        """Advance durations by one turn; return the effects that expired."""
        target = self._resolve_target(target)
        effects = target.get("status_effects", [])
        expired = []
        for entry in list(effects):
            entry["remaining"] -= 1
            if entry["remaining"] <= 0:
                effects.remove(entry)
                expired.append(entry)
        target["statuses"] = [e["type"] for e in effects]
        return expired

    def dispel_status_effects(self, target=None, effect_type=None):
        """Remove status effects (all, or one type); return the removed ones."""
        target = self._resolve_target(target)
        effects = target.get("status_effects", [])
        removed = [e for e in effects
                   if effect_type is None or e["type"] == effect_type]
        effects[:] = [e for e in effects if e not in removed]
        target["statuses"] = [e["type"] for e in effects]
        return removed

    # ------------------------------------------------------------------
    # Area of effect
    # ------------------------------------------------------------------
    def calculate_aoe(self, center=None, radius=5.0, targets=None, caster=None,
                      base_damage=100, friendly_fire=False, min_falloff=0.5):
        """Resolve a circular AoE around ``center``.

        Only targets inside ``radius`` (Euclidean distance) are hit.
        Damage falls off linearly from full at the center to
        ``min_falloff`` at the edge. The caster and, unless
        ``friendly_fire`` is set, the caster's teammates are excluded.
        """
        center = center or {"x": 0.0, "y": 0.0}
        targets = targets or []
        caster = caster or {}
        caster_team = caster.get("team")
        caster_id = caster.get("id")

        hits = []
        for target in targets:
            if caster_id is not None and target.get("id") == caster_id:
                continue
            if (not friendly_fire and caster_team is not None
                    and target.get("team") == caster_team):
                continue

            pos = target.get("position", target)
            dx = pos.get("x", 0.0) - center.get("x", 0.0)
            dy = pos.get("y", 0.0) - center.get("y", 0.0)
            distance = math.hypot(dx, dy)
            if distance > radius:
                continue

            if radius > 0:
                falloff = 1.0 - (distance / radius) * (1.0 - min_falloff)
            else:
                falloff = 1.0
            damage = max(1, int(round(base_damage * falloff)))
            hits.append({
                "target": target,
                "distance": distance,
                "falloff": falloff,
                "damage": damage,
            })
        return hits

    # ------------------------------------------------------------------
    # Combat log
    # ------------------------------------------------------------------
    def log_combat_event(self, event=None, **fields):
        """Append a structured event (damage / skill / status / ...)."""
        event = dict(event or {})
        event.update(fields)
        event.setdefault("type", "damage")
        event.setdefault("time", time.time())
        event["seq"] = len(self.combat_log)
        self.combat_log.append(event)
        return event

    def get_combat_log(self, event_type=None, actor=None, target=None):
        """Return logged events, optionally filtered by type/actor/target."""
        return [
            e for e in self.combat_log
            if (event_type is None or e.get("type") == event_type)
            and (actor is None or e.get("actor") == actor)
            and (target is None or e.get("target") == target)
        ]

    def replay_combat_log(self, event_type=None):
        """Return the recorded fight as an ordered list of readable lines."""
        return [self._format_event(e)
                for e in self.get_combat_log(event_type=event_type)]

    @staticmethod
    def _format_event(event):
        seq = event["seq"]
        kind = event.get("type")
        if kind == "damage":
            return (f"#{seq} {event.get('actor', '?')} hits "
                    f"{event.get('target', '?')} for "
                    f"{event.get('damage', 0)} "
                    f"{event.get('damage_type', '')} damage")
        if kind == "skill":
            return (f"#{seq} {event.get('actor', '?')} casts "
                    f"{event.get('skill', '?')}")
        if kind == "status":
            return (f"#{seq} {event.get('target', '?')} gains "
                    f"{event.get('effect', '?')} "
                    f"({event.get('duration', '?')} turns)")
        return f"#{seq} {kind}: {event}"
