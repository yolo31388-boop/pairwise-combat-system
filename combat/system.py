"""pairwise-combat-system - CombatSystem

Core combat system: damage calculation, hit resolution, status effects,
AOE resolution and combat logging.

Entities are plain dicts, e.g.::

    attacker = {"name": "Warrior", "level": 12, "attack": 60,
                "hit_rate": 0.9, "crit_rate": 0.25}
    target = {"name": "Slime", "level": 10, "defense": 20,
              "magic_resist": 5, "dodge": 0.1, "block_chance": 0.15,
              "status_effects": [], "team": "enemy", "x": 3.0, "y": 4.0}
"""

from __future__ import annotations

import math
import random

DAMAGE_TYPES = ("physical", "magical")

# Effects that make a target immune to all damage.
INVINCIBLE_EFFECTS = frozenset({"invincible", "invulnerable", "immune"})
# Effects that make a target dodge every incoming attack.
DODGE_EFFECTS = frozenset({"dodge", "evasion", "evading"})

LOG_LEVELS = {"debug": 10, "info": 20, "important": 30}

DEFAULT_MAX_STACKS = 3
DEFAULT_EFFECT_DURATION = 3
LEVEL_HIT_MODIFIER = 0.02  # +/-2% hit chance per level of difference


def _effects_of(entity):
    if not isinstance(entity, dict):
        return []
    effects = entity.get("status_effects") or entity.get("effects") or []
    return [e for e in effects if isinstance(e, dict)]


def _effect_names(entity):
    return {str(e.get("name", "")).lower() for e in _effects_of(entity)}


def _position_of(entity):
    """Extract an (x, y) position from a tuple/list or an entity dict."""
    if isinstance(entity, (tuple, list)) and len(entity) >= 2:
        return float(entity[0]), float(entity[1])
    if isinstance(entity, dict):
        pos = entity.get("position")
        if isinstance(pos, (tuple, list)) and len(pos) >= 2:
            return float(pos[0]), float(pos[1])
        return float(entity.get("x", 0.0)), float(entity.get("y", 0.0))
    return 0.0, 0.0


class CombatSystem:
    def __init__(self, *, seed=None, variance=0.1):
        self.state = {}
        self.variance = variance
        self._rng = random.Random(seed)
        self._log = []
        self._turn = 0

    # ------------------------------------------------------------------
    # Damage
    # ------------------------------------------------------------------
    def calculate_damage(self, attacker=None, target=None, skill=None,
                         damage_type=None, base_damage=None):
        """Compute damage dealt to ``target``.

        - Checks target state: invincible or dodging targets take 0 damage.
        - Damage types: physical is mitigated by defense/armor, magical by
          magic_resist/resistance.
        - Damage variance: each roll is randomly scaled within
          +/- ``variance`` so repeated hits are not identical.
        """
        skill = skill if isinstance(skill, dict) else {}
        dtype = str(damage_type or skill.get("type") or "physical").lower()
        if dtype not in DAMAGE_TYPES:
            raise ValueError(f"unknown damage type: {dtype!r}")

        # Target state: invincible / dodging targets take no damage.
        if self.is_invincible(target) or self.is_dodging(target):
            return 0

        if base_damage is None:
            base_damage = skill.get("damage", skill.get("power"))
        if base_damage is None and isinstance(attacker, dict):
            stat = "attack" if dtype == "physical" else "magic_attack"
            base_damage = attacker.get(stat, attacker.get("attack", 0))
        base = float(base_damage or 0)

        # Damage type mitigation.
        tgt = target if isinstance(target, dict) else {}
        if dtype == "physical":
            defense = float(tgt.get("defense", tgt.get("armor", 0)) or 0)
        else:
            defense = float(tgt.get("magic_resist", tgt.get("resistance", 0)) or 0)
        mitigated = base * (100.0 / (100.0 + max(0.0, defense)))

        # Damage variance: random float per hit.
        spread = float(skill.get("variance", self.variance))
        rolled = mitigated * self._rng.uniform(1.0 - spread, 1.0 + spread)
        return max(0, int(round(rolled)))

    @staticmethod
    def is_invincible(target):
        if isinstance(target, dict) and target.get("invincible"):
            return True
        return bool(_effect_names(target) & INVINCIBLE_EFFECTS)

    @staticmethod
    def is_dodging(target):
        if isinstance(target, dict) and target.get("dodging"):
            return True
        return bool(_effect_names(target) & DODGE_EFFECTS)

    # ------------------------------------------------------------------
    # Hit resolution
    # ------------------------------------------------------------------
    def check_hit(self, attacker=None, target=None, skill=None, hit_rate=None):
        """Resolve an attack against a target.

        - Hit chance factors in the target's dodge and the level
          difference between attacker and target, not just raw hit rate.
        - Crit roll: a 100% crit rate always crits.
        - Block roll: the target's block chance can reduce the damage.

        Returns a result dict with hit/crit/blocked flags and the final
        damage multiplier.
        """
        atk = attacker if isinstance(attacker, dict) else {}
        tgt = target if isinstance(target, dict) else {}
        skill = skill if isinstance(skill, dict) else {}

        if hit_rate is None:
            hit_rate = skill.get("hit_rate",
                                 atk.get("hit_rate", atk.get("accuracy", 0.9)))
        dodge = float(tgt.get("dodge", tgt.get("evasion", 0.0)) or 0.0)
        level_delta = int(atk.get("level", 1)) - int(tgt.get("level", 1))
        hit_chance = float(hit_rate) - dodge + LEVEL_HIT_MODIFIER * level_delta
        hit_chance = min(1.0, max(0.05, hit_chance))
        hit = self._rng.random() < hit_chance

        # Crit: crit_rate >= 1.0 (100%) always crits.
        crit_rate = float(skill.get("crit_rate", atk.get("crit_rate", 0.0)) or 0.0)
        crit = bool(hit and (crit_rate >= 1.0 or self._rng.random() < crit_rate))
        crit_multiplier = float(skill.get(
            "crit_multiplier", atk.get("crit_multiplier", 1.5)))

        # Block: blocked hits lose a fraction of their damage.
        block_chance = float(tgt.get("block_chance", tgt.get("block", 0.0)) or 0.0)
        blocked = bool(hit and self._rng.random() < block_chance)
        block_reduction = float(tgt.get("block_reduction", 0.5)) if blocked else 0.0

        multiplier = (crit_multiplier if crit else 1.0) * (1.0 - block_reduction)
        return {
            "hit": hit,
            "hit_chance": hit_chance,
            "crit": crit,
            "crit_multiplier": crit_multiplier if crit else 1.0,
            "blocked": blocked,
            "block_reduction": block_reduction,
            "damage_multiplier": multiplier,
        }

    # ------------------------------------------------------------------
    # Status effects
    # ------------------------------------------------------------------
    def apply_status_effect(self, target=None, effect=None, *, name=None,
                            duration=None, max_stacks=None, stackable=None):
        """Apply a status effect to ``target``.

        - Duration: every effect ticks down and expires via
          :meth:`tick_status_effects`.
        - Stacking: re-applying an existing effect refreshes its duration
          and only adds stacks up to ``max_stacks`` (never unlimited).
        - Dispel: effects can be removed with :meth:`dispel_status_effects`;
          effects marked ``dispellable=False`` resist cleansing.
        """
        eff = dict(effect) if isinstance(effect, dict) else {}
        if name is not None:
            eff["name"] = name
        eff.setdefault("name", "unknown")
        eff["duration"] = int(duration if duration is not None
                              else eff.get("duration", DEFAULT_EFFECT_DURATION))
        limit = int(max_stacks if max_stacks is not None
                    else eff.get("max_stacks", DEFAULT_MAX_STACKS))
        if stackable is None:
            stackable = bool(eff.get("stackable", limit > 1))

        if not isinstance(target, dict):
            return {"applied": False, "effect": eff, "reason": "no target"}

        effects = target.setdefault("status_effects", [])
        existing = next((e for e in effects
                         if e.get("name") == eff["name"]), None)
        if existing is not None:
            # Stacking rule: refresh duration, cap stacks at max_stacks.
            existing["duration"] = eff["duration"]
            existing["remaining"] = eff["duration"]
            if stackable:
                existing["stacks"] = min(existing.get("stacks", 1) + 1, limit)
            return {"applied": True, "effect": existing, "refreshed": True,
                    "stacks": existing.get("stacks", 1)}

        eff["remaining"] = eff["duration"]
        eff["stacks"] = 1
        effects.append(eff)
        return {"applied": True, "effect": eff, "refreshed": False, "stacks": 1}

    def tick_status_effects(self, target):
        """Advance all status effects on ``target`` by one turn.

        Effects whose remaining duration reaches zero expire and are
        removed. Returns the list of expired effects.
        """
        effects = _effects_of(target)
        expired = []
        kept = []
        for eff in effects:
            eff["remaining"] = int(eff.get("remaining",
                                           eff.get("duration", 0))) - 1
            if eff["remaining"] > 0:
                kept.append(eff)
            else:
                expired.append(eff)
        if isinstance(target, dict):
            target["status_effects"] = kept
        return expired

    def dispel_status_effects(self, target, *, names=None, count=None,
                              dispellable_only=True):
        """Remove status effects from ``target`` (cleanse/purify).

        ``names`` restricts removal to specific effect names, ``count``
        caps how many effects are removed, and effects marked
        ``dispellable=False`` are immune unless ``dispellable_only`` is
        disabled. Returns the removed effects.
        """
        if not isinstance(target, dict):
            return []
        wanted = {n.lower() for n in names} if names else None
        removed, kept = [], []
        for eff in _effects_of(target):
            match = wanted is None or str(eff.get("name", "")).lower() in wanted
            blocked = dispellable_only and not eff.get("dispellable", True)
            full = count is not None and len(removed) >= count
            if match and not blocked and not full:
                removed.append(eff)
            else:
                kept.append(eff)
        target["status_effects"] = kept
        return removed

    # ------------------------------------------------------------------
    # AOE
    # ------------------------------------------------------------------
    def calculate_aoe(self, center=None, targets=None, radius=5.0,
                      base_damage=0.0, caster=None, friendly_fire=False,
                      falloff=0.5):
        """Resolve a circular AOE around ``center``.

        - Circular range check: a target is hit only when its distance to
          the center is within ``radius`` (no square corners).
        - Damage falloff: damage scales linearly from 100% at the center
          down to ``1 - falloff`` at the edge.
        - Friendly fire: allies of ``caster`` (same ``team``) are skipped
          unless ``friendly_fire`` is enabled.
        """
        cx, cy = _position_of(center if center is not None else (0.0, 0.0))
        radius = float(radius)
        caster_team = caster.get("team") if isinstance(caster, dict) else None

        hits = []
        for t in targets or []:
            tx, ty = _position_of(t)
            distance = math.hypot(tx - cx, ty - cy)
            if distance > radius:
                continue
            if (not friendly_fire and caster_team is not None
                    and isinstance(t, dict) and t.get("team") == caster_team):
                continue
            scale = 1.0 - falloff * (distance / radius) if radius > 0 else 1.0
            scale = max(0.0, min(1.0, scale))
            hits.append({
                "target": t,
                "distance": distance,
                "damage_multiplier": scale,
                "damage": base_damage * scale,
            })
        return {
            "center": (cx, cy),
            "radius": radius,
            "hits": hits,
            "hit_count": len(hits),
            "total_damage": sum(h["damage"] for h in hits),
        }

    # ------------------------------------------------------------------
    # Combat log
    # ------------------------------------------------------------------
    def log_combat_event(self, event=None, **fields):
        """Record a combat event (skill, damage, status, ...).

        Events keep the skill name, status changes and participants, not
        just a damage number. Use :meth:`get_combat_log` for filtered
        views and :meth:`replay` to review the fight afterwards.
        """
        entry = dict(event) if isinstance(event, dict) else {}
        entry.update(fields)
        entry.setdefault("type", "info")
        entry.setdefault("level", "info")
        entry.setdefault("turn", self._turn)
        entry["seq"] = len(self._log)
        self._log.append(entry)
        return entry

    def get_combat_log(self, *, event_type=None, min_level=None, limit=None):
        """Filtered view of the combat log.

        ``event_type`` keeps only events of that type (e.g. ``"damage"``),
        ``min_level`` drops entries below the given importance, and
        ``limit`` keeps only the most recent N entries.
        """
        entries = self._log
        if event_type is not None:
            entries = [e for e in entries if e.get("type") == event_type]
        if min_level is not None:
            threshold = LOG_LEVELS.get(min_level, LOG_LEVELS["info"])
            entries = [e for e in entries
                       if LOG_LEVELS.get(e.get("level", "info"), 20) >= threshold]
        if limit is not None:
            entries = entries[-int(limit):]
        return list(entries)

    def replay(self, *, event_type=None, min_level=None):
        """Replay the battle as formatted, chronological lines."""
        return [self._format_event(e)
                for e in self.get_combat_log(event_type=event_type,
                                             min_level=min_level)]

    def next_turn(self):
        self._turn += 1
        return self._turn

    def clear_log(self):
        self._log.clear()
        self._turn = 0

    @staticmethod
    def _format_event(entry):
        parts = [f"[turn {entry.get('turn', 0)}]", str(entry.get("type", "info"))]
        skill = entry.get("skill")
        if skill:
            parts.append(f"skill={skill}")
        actor = entry.get("attacker") or entry.get("source")
        target = entry.get("target")
        if actor or target:
            parts.append(f"{actor or '?'} -> {target or '?'}")
        if "damage" in entry:
            parts.append(f"damage={entry['damage']}")
        if entry.get("crit"):
            parts.append("CRIT")
        if entry.get("blocked"):
            parts.append("BLOCKED")
        status = entry.get("status") or entry.get("effect")
        if status:
            parts.append(f"status={status}")
        return " ".join(parts)
