"""Public combat context, legal decisions, and input sequences for Bot-C."""
from typing import NamedTuple

from sf import config
from sf.combat import ATTACKS


WINDOW = 5
HELD_MOVES = {"wait", "advance", "retreat", "guard", "crouch"}
GROUND_ATTACKS = ("quick_punch", "kick_low", "crouch_punch", "crouch_attack",
                  "punch", "uppercut", "upper_kick", "hadouken", "shoryuken")
AIR_ATTACKS = ("air_punch", "air_kick", "punch_down")
GROUND_MOVES = ("wait", "advance", "retreat", "guard", "crouch",
                "jump", "jump_in", "jump_out") + GROUND_ATTACKS
AIR_MOVES = ("wait", "advance", "retreat") + AIR_ATTACKS
INPUT_SEQUENCE = {
    "wait": ((),),
    "advance": (("toward",),),
    "retreat": (("away",),),
    "guard": (("block",),),
    "crouch": (("down",),),
    "jump": (("jump",),),
    "jump_in": (("toward", "jump"),),
    "jump_out": (("away", "jump"),),
    "quick_punch": (("lp",),),
    "kick_low": (("lk",),),
    "crouch_punch": (("down", "lp"),),
    "crouch_attack": (("down", "hk"),),
    "punch": (("hp",),),
    "uppercut": (("toward", "hp"),),
    "upper_kick": (("hk",),),
    "hadouken": (("down",), ("toward", "lp")),
    "shoryuken": (("toward",), ("down",), ("toward", "lp")),
    "air_punch": (("lp",),),
    "air_kick": (("hk",),),
    "punch_down": (("hp",),),
}


class Context(NamedTuple):
    phase: str
    distance: str
    mode: str
    danger: bool
    wall: bool


def wall_space(fighter):
    return min(fighter.x - config.STAGE_MARGIN,
               config.CANVAS_W - config.STAGE_MARGIN - fighter.x)


def attack_range(name):
    return ATTACKS[name].reach + 22 + config.HURTBOX_W / 2


JAB_RANGE = attack_range("quick_punch")
LONG_RANGE = attack_range("upper_kick")


def context_for(world, side, mode):
    fighter, opponent = world.fighters[side], world.fighters[1 - side]
    distance = abs(fighter.x - opponent.x)
    near_wall = wall_space(fighter) < 95
    opponent_wall = wall_space(opponent) < 95
    if distance <= LONG_RANGE and fighter.knocked_down and fighter.hitstun <= 12:
        phase = "wake"
    elif distance <= LONG_RANGE and opponent.knocked_down and opponent.hitstun <= 12:
        phase = "pressure"
    elif distance <= LONG_RANGE + 45 and (near_wall or opponent_wall):
        phase = "cornered" if near_wall else "corner_pressure"
    else:
        phase = "neutral"
    band = "close" if distance <= JAB_RANGE else "mid" if distance <= LONG_RANGE else "far"
    danger = False
    if opponent.attack and not opponent.hit_connected:
        ahead = max(0, opponent.attack.startup - opponent.attack_tick)
        if ahead <= 7:
            box = opponent.get_hitbox(ahead=ahead)
            danger = bool(box and box.colliderect(fighter.hurtbox().inflate(60, 48)))
    if not danger:
        danger = any(p.owner != side and 0 < (fighter.x - p.x) * p.direction <= 140
                     and fighter.y - config.HURTBOX_H <= p.y <= fighter.y
                     for p in world.projectiles)
    return Context(phase, band, mode, danger, near_wall or opponent_wall)


def legal_moves(world, side, mode):
    if mode is None:
        return ("wait",)
    if mode.startswith("ground"):
        moves = ("wait",) + GROUND_ATTACKS if mode.endswith("cancel") else GROUND_MOVES
        if any(p.owner == side for p in world.projectiles):
            moves = tuple(move for move in moves if move != "hadouken")
        return moves
    if not mode.endswith("cancel") and world.fighters[side].anim.name == "jump":
        return AIR_MOVES
    return ("wait",) + AIR_ATTACKS


def candidates(world, side, context, legal):
    fighter, opponent = world.fighters[side], world.fighters[1 - side]
    can_cancel = context.mode.endswith("cancel")
    if context.mode.startswith("air"):
        moves = ("air_kick", "punch_down", "advance", "wait")
        if abs(fighter.x - opponent.x) > LONG_RANGE:
            moves = ("advance", "wait")
    elif context.danger and not can_cancel:
        moves = ("guard", "quick_punch", "kick_low", "retreat", "jump_out")
    elif context.phase == "pressure":
        moves = ("quick_punch", "crouch_attack", "guard", "wait", "advance")
        if opponent.hitstun > ATTACKS["quick_punch"].startup + 2:
            moves = ("wait", "advance", "crouch_attack", "guard")
    elif not opponent.on_ground and context.distance != "far":
        moves = ("uppercut", "guard", "retreat", "wait")
    elif context.phase in ("wake", "cornered"):
        moves = ("quick_punch", "guard", "kick_low", "jump_in", "wait")
    elif context.phase == "corner_pressure" and context.distance != "far":
        moves = ("crouch_attack", "kick_low", "quick_punch", "guard", "advance")
    elif context.distance == "far":
        moves = ("advance", "wait", "jump_in")
        if fighter.health > opponent.health and world.timer <= 8:
            moves = ("wait", "retreat", "advance")
    elif context.distance == "mid":
        moves = ("advance", "crouch_attack", "kick_low", "upper_kick", "guard")
    elif opponent.is_crouching:
        moves = ("crouch_attack", "crouch_punch", "kick_low", "guard", "retreat")
    else:
        moves = ("upper_kick", "quick_punch", "crouch_attack", "guard", "retreat")
    return tuple(move for move in moves if move in legal) or ("wait",)


def prior(context, legal):
    weights = dict.fromkeys(legal, 0.6)
    if context.mode.startswith("air"):
        preferred = ("advance", "wait") if context.distance == "far" else ("air_kick", "wait")
    elif context.phase == "wake" or context.danger:
        preferred = ("guard", "quick_punch", "jump_in")
    elif context.distance == "far":
        preferred = ("advance", "advance", "wait", "hadouken")
    elif context.phase == "pressure":
        preferred = ("quick_punch", "crouch_attack", "wait")
    else:
        preferred = ("quick_punch", "kick_low", "advance", "guard")
    for move in preferred:
        if move in weights:
            weights[move] += 2.0
    total = sum(weights.values())
    return tuple(weights[move] / total for move in legal)


def commands(move, age, fighter, opponent):
    sequence = INPUT_SEQUENCE[move]
    if move in HELD_MOVES:
        age = 0
    if age >= len(sequence):
        return ()
    toward = "right" if opponent.x >= fighter.x else "left"
    away = "left" if toward == "right" else "right"
    return tuple(toward if key == "toward" else away if key == "away" else key
                 for key in sequence[age])
