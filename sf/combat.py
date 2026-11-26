from dataclasses import dataclass


@dataclass(frozen=True)
class Attack:
    anim: str
    startup: int        # ticks before the hit becomes active
    active: int         # ticks the hitbox is live
    damage: int
    hitstun: int
    blockstun: int
    knockback: float    # horizontal shove applied to the victim
    reach: int          # hitbox length in front of the fighter (px)
    y: int              # hitbox center height above the feet (px)
    h: int              # hitbox height (px)
    heavy: bool = False # heavy hits: longer hitstop, screen shake, knockdown
    cancel_into: tuple[str, ...] = ()  # allowed specials after a clean hit
    sound: str = "punch"
    air: bool = False
    knockdown_stun: int = 48


LIGHT_CANCELS = ("shoryuken", "hadouken")


ATTACKS = {
    # Ground lights
    "quick_punch": Attack("quick_punch", 4, 6, 12, 14, 9, 4.0, 110, 165, 52, cancel_into=LIGHT_CANCELS),
    "kick_low":    Attack("kick_low",    6, 6, 18, 16, 10, 5.0, 155, 55, 55,
                          cancel_into=LIGHT_CANCELS, sound="kick"),

    # Ground heavies
    # Ryu's fastest repeat can hit 31 active ticks after a last-active-frame hit.
    "punch":       Attack("punch",      8, 6, 25, 20, 12, 7.0, 145, 165, 58,
                          heavy=True, knockdown_stun=30),
    "uppercut":    Attack("uppercut",   7, 7, 30, 24, 12, 7.5, 115, 180, 95, heavy=True),
    "upper_kick":  Attack("upper_kick", 10, 8, 35, 26, 14, 9.0, 165, 170, 85, heavy=True, sound="kick"),

    # Crouch attacks
    "crouch_punch":  Attack("crouch_punch",  4, 5, 12, 14, 8, 3.5, 115, 95, 50,
                             cancel_into=LIGHT_CANCELS),
    "crouch_attack": Attack("crouch_attack", 8, 6, 24, 26, 12, 6.5, 155, 35, 50, heavy=True, sound="kick"),

    # Air attacks
    "air_punch":   Attack("air_punch",  5, 10, 20, 18, 10, 5.0, 115, 130, 62, air=True),
    "air_kick":    Attack("air_kick",   6, 10, 28, 22, 12, 7.0, 145, 105, 62, heavy=True, air=True, sound="kick"),
    "punch_down":  Attack("punch_down", 5, 10, 22, 18, 10, 5.0, 100, 90, 72, air=True),
}

# Special moves (motion inputs). For hadouken, `startup` is the tick the
# fireball spawns and `active` is 0 — the projectile carries the hit, not
# the body. Shoryuken's hitbox rides up with the fighter while he rises.
SPECIALS = {
    "hadouken":  Attack("punch",    10, 0, 22, 18, 12, 5.5, 0, 150, 50),
    "shoryuken": Attack("uppercut", 3, 16, 38, 26, 16, 9.0, 95, 150, 170, heavy=True),
}

FIREBALL_SPEED = 8.5
SHORYUKEN_RISE = -19.0     # initial vertical velocity
SHORYUKEN_DRIFT = 4.5      # forward velocity while rising
SHORYUKEN_LANDING_LAG = 12

HITSTOP_LIGHT = 6          # frozen ticks on a connected light hit
HITSTOP_HEAVY = 11
HITSTOP_BLOCK = 4
