"""Translate controller commands to the same keys used by human players."""

PRESS_ACTIONS = {"jump", "lp", "hp", "lk", "hk"}


def encode_actions(actions, controls):
    held = {key: action in actions for action, key in controls.items()}
    pressed = {controls[action] for action in actions if action in PRESS_ACTIONS}
    return held, pressed
