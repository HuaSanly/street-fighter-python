"""Bot-C 使用的局势特征、动作候选与逐帧输入指令。"""
from typing import NamedTuple

from sf import config
from sf.combat import ATTACKS


# 观察和持续输入都以五个有效战斗帧为基本窗口。
WINDOW = 5
HELD_MOVES = {"wait", "advance", "retreat", "guard", "crouch"}
GROUND_ATTACKS = ("quick_punch", "kick_low", "crouch_punch", "crouch_attack",
                  "punch", "uppercut", "upper_kick", "hadouken", "shoryuken")
AIR_ATTACKS = ("air_punch", "air_kick", "punch_down")
ATTACK_ACTIONS = frozenset(GROUND_ATTACKS + AIR_ATTACKS)
GROUND_MOVES = ("wait", "advance", "retreat", "guard", "crouch",
                "jump", "jump_in", "jump_out") + GROUND_ATTACKS
AIR_MOVES = ("wait", "advance", "retreat") + AIR_ATTACKS
# 每个序列元素对应一帧输入。toward 和 away 在执行时按双方位置换算成左右键。
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
    """从指定一方视角描述离散局势，用于模型分组和生成动作候选。"""

    phase: str
    distance: str
    mode: str
    danger: bool
    wall: bool


def wall_space(fighter):
    return min(fighter.x - config.STAGE_MARGIN,
               config.CANVAS_W - config.STAGE_MARGIN - fighter.x)


def attack_range(name):
    # 估算两名角色中心的水平距离，计入出招框起点偏移和受击框半宽。
    return ATTACKS[name].reach + 22 + config.HURTBOX_W / 2


JAB_RANGE = attack_range("quick_punch")
LONG_RANGE = attack_range("upper_kick")


def context_for(world, side, mode):
    """识别主情景，再附加距离档位、行动模式、威胁和版边信息。"""
    fighter, opponent = world.fighters[side], world.fighters[1 - side]
    distance = abs(fighter.x - opponent.x)
    near_wall = wall_space(fighter) < 95
    opponent_wall = wall_space(opponent) < 95
    # 在近身时优先识别起身攻防，因此版边起身沿用起身情景，同时保留版边标记。
    if distance <= LONG_RANGE and fighter.knocked_down and fighter.hitstun <= 12:
        phase = "wake"
    elif distance <= LONG_RANGE and opponent.knocked_down and opponent.hitstun <= 12:
        phase = "pressure"
    elif distance <= LONG_RANGE + 45 and (near_wall or opponent_wall):
        phase = "cornered" if near_wall else "corner_pressure"
    else:
        phase = "neutral"
    band = "close" if distance <= JAB_RANGE else "mid" if distance <= LONG_RANGE else "far"
    # 用即将生效的攻击框和逼近的飞行道具估计威胁，实际命中由战斗引擎结算。
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
    """按当前行动权过滤动作类型，为对手分布与 Bot 候选提供统一边界。"""
    if mode is None:
        return ("wait",)
    if mode.startswith("ground"):
        if mode == "ground_cancel":
            moves = ("wait",) + world.fighters[side].cancel_targets()
        else:
            moves = GROUND_MOVES
        # 同一方只能有一个波动拳飞行道具在场。
        if any(p.owner == side for p in world.projectiles):
            moves = tuple(move for move in moves if move != "hadouken")
        return moves
    if not mode.endswith("cancel") and world.fighters[side].anim.name == "jump":
        # 直跳可以空中微调方向，空翻维持原有轨迹。
        return AIR_MOVES
    return ("wait",) + AIR_ATTACKS


def candidates(world, side, context, legal):
    """按战术情景挑出少量动作。过滤后首项也作为规则回退与模拟续演动作。"""
    if context.mode == "ground_cancel":
        return legal
    fighter, opponent = world.fighters[side], world.fighters[1 - side]
    if context.mode.startswith("air"):
        moves = ("air_kick", "punch_down", "advance", "wait")
        if abs(fighter.x - opponent.x) > LONG_RANGE:
            moves = ("advance", "wait")
    elif context.danger:
        moves = ("guard", "quick_punch", "kick_low", "retreat", "jump_out")
    elif context.phase == "pressure":
        moves = ("quick_punch", "crouch_attack", "guard", "wait", "advance")
        # 对手离恢复行动还早时，优先等时机，再比较立刻出招等替代方案。
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
    """按情景给合法动作设置冷启动权重，再归一化为概率。"""
    # 每个合法动作都有基础权重，保留对低频行为的预测与采样机会。
    weights = dict.fromkeys(legal, 0.6)
    if context.mode.startswith("air"):
        preferred = ("advance", "wait") if context.distance == "far" else ("air_kick", "wait")
    elif context.phase == "wake" or context.danger:
        preferred = ("guard", "quick_punch", "jump_in")
    elif context.distance == "far":
        # 两次加权让前进成为远距离时更强的默认假设。
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
    """取当前帧的按键序列，持续动作每帧复用同一组按键。"""
    sequence = INPUT_SEQUENCE[move]
    if move in HELD_MOVES:
        age = 0
    if age >= len(sequence):
        return ()
    toward = "right" if opponent.x >= fighter.x else "left"
    away = "left" if toward == "right" else "right"
    return tuple(toward if key == "toward" else away if key == "away" else key
                 for key in sequence[age])
