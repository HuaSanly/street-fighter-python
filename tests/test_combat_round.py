import random
import unittest

from sf import config
from sf.combat import ATTACKS, SPECIALS, FIREBALL_SPEED
from sf.combat_round import CombatRound, SILENT_SOUNDS
from sf.effects import Effects, Fireball
from sf.fighter import Fighter


def make_round(effects=None):
    names = {"idle", "parry_b", "parry_f", "crouch", "front_flip", "recover",
             "knockback", "hit_stand"} | set(ATTACKS)
    anims = {name: {"frames": [None] * 6, "delay": 3, "loop": False,
                    "hold": False, "next": None} for name in names}
    controls = {key: key for key in ("left", "right", "down", "lp", "hp", "lk",
                                      "hk", "jump", "block")}
    return CombatRound([Fighter("ryu", anims, 200, 1, controls, SILENT_SOUNDS),
                        Fighter("ken", anims, 305, -1, controls, SILENT_SOUNDS)],
                       effects=effects)


def inputs(*actions):
    controls = ("left", "right", "down", "lp", "hp", "lk", "hk", "jump", "block")
    return {key: key in actions for key in controls}, frozenset(actions)


class CombatRoundTests(unittest.TestCase):
    def test_forward_round_matches_live_and_is_independent(self):
        live = make_round(Effects())
        live.projectiles.append(Fireball(125, config.GROUND_Y - 128, 1, 0,
                                         ((1, 1, 1),) * 3, SPECIALS["hadouken"], FIREBALL_SPEED))
        branch = live.fork()
        self.assertIsNot(live.projectiles[0], branch.projectiles[0])
        for tick in range(85):
            pair = (inputs("hk") if tick == 0 else inputs(),
                    inputs("block") if tick < 8 else inputs())
            before = random.getstate()
            branch.step(pair)
            self.assertEqual(random.getstate(), before)
            live.step(pair)
            for a, b in zip(live.fighters, branch.fighters):
                self.assertEqual((a.x, a.y, a.health, a.hitstun, a.blockstun, a.attack,
                                  a.attack_tick, a.anim.frame_index, a.dir_history),
                                 (b.x, b.y, b.health, b.hitstun, b.blockstun, b.attack,
                                  b.attack_tick, b.anim.frame_index, b.dir_history))
            self.assertEqual((live.hitstop, live.timer, live.combo),
                             (branch.hitstop, branch.timer, branch.combo))
            self.assertEqual([(p.x, p.age) for p in live.projectiles],
                             [(p.x, p.age) for p in branch.projectiles])
        self.assertLess(live.fighters[1].health, config.MAX_HEALTH)
        self.assertEqual(branch.effects, None)

    def test_fork_for_a_bot_hides_unfinished_opponent_motion(self):
        live = make_round()
        for fighter in live.fighters:
            fighter.dir_history.append(("d", 1))
        branch = live.fork(viewer=1)
        self.assertFalse(branch.fighters[0].dir_history)
        self.assertEqual(list(branch.fighters[1].dir_history), [("d", 1)])
        self.assertTrue(live.fighters[0].dir_history)

    def test_timer_keeps_running_during_hitstop(self):
        fight = make_round()
        fight.timer = 1
        fight.second_ticks = config.FPS - 1
        fight.hitstop = 2
        fight.fighters[1].health -= 1
        fight.step((inputs("lp"), inputs()))
        self.assertTrue(fight.finished and fight.timed_out)
        self.assertEqual(fight.winner, 0)
        self.assertIsNone(fight.fighters[0].attack)
