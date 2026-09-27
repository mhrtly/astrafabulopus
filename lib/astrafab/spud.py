"""Tuber-grade presentation. Every string a human reads passes through here, so the machine-readable
lines elsewhere stay boring on purpose. Set AF_PLAIN=1 to take the potatoes out entirely."""
import random

from . import core

# pressure level -> (emoji, potato state, what it means)
LEVELS = {
    "plenty":  ("🥔", "raw & plentiful", "plenty of headroom"),
    "watch":   ("🍟", "frying",          "fine for now; mind the pace"),
    "tight":   ("🔥", "crispy",          "running low; route around it"),
    "empty":   ("💀", "burnt",           "limit reached; this budget's lanes are unavailable"),
    "unknown": ("❔", "in the dark",     "no reading yet; unknown is not zero"),
}
LEVEL_ORDER = ["plenty", "unknown", "watch", "tight", "empty"]

QUIPS = [
    "The Council has been informed. The Council is always informed.",
    "Remember: every token was once a tiny potato with a dream.",
    "Be excellent to each other, preferably while eating carbs.",
    "The early spud gets the butter.",
    "We'll burn that bridge when we fry it.",
    "Unknown is not zero. Unknown is a potato you haven't dug up yet.",
    "Budgets are just soil. Plant wisely.",
    "You are doing great, spudling. The pantry says so.",
]


def worst(levels):
    levels = [lv for lv in levels if lv in LEVEL_ORDER] or ["unknown"]
    return max(levels, key=LEVEL_ORDER.index)


def emoji(level):
    if core.plain_mode():
        return ""
    return LEVELS.get(level, LEVELS["unknown"])[0]


def state(level):
    return LEVELS.get(level, LEVELS["unknown"])[1]


def meaning(level):
    return LEVELS.get(level, LEVELS["unknown"])[2]


def gauge(used, width=20):
    """Remaining-fuel bar: filled = what is LEFT, because that is what you plan with."""
    if used is None:
        return "·" * width
    left = max(0.0, min(100.0, 100.0 - used))
    filled = int(round(left / 100.0 * width))
    if core.plain_mode():
        return "#" * filled + "-" * (width - filled)
    return "█" * filled + "░" * (width - filled)


def talent_bar(score, width=10):
    if score is None:
        return "?" * 3
    filled = int(round(max(0.0, min(10.0, float(score))) / 10.0 * width))
    if core.plain_mode():
        return "#" * filled + "." * (width - filled)
    return "●" * filled + "○" * (width - filled)


def quip(seed=None):
    if core.plain_mode():
        return ""
    rng = random.Random(seed)
    return rng.choice(QUIPS)


def banner(title):
    if core.plain_mode():
        return title
    return "✨🥔✨ %s ✨🥔✨" % title
