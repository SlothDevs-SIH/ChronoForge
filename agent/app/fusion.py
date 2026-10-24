"""Evidence fusion in log-odds space.

Each Evidence carries a likelihood_ratio = P(evidence | not fixed) / P(evidence | fixed).
logit(posterior) = logit(prior) + sum(ln(LR_i)). Assumes independent checks (approximation; say so in the deck).
"""
import math
from typing import Iterable

from . import config

_EPS = 1e-6


def logit(p: float) -> float:
    p = min(max(p, _EPS), 1 - _EPS)
    return math.log(p / (1 - p))


def sigmoid(x: float) -> float:
    return 1 / (1 + math.exp(-x))


def fuse(prior: float, likelihood_ratios: Iterable[float]) -> float:
    total = logit(prior)
    for lr in likelihood_ratios:
        total += math.log(max(lr, _EPS))
    return sigmoid(total)


def verdict_state(posterior: float) -> str:
    if posterior >= config.NOT_FIXED_AT:
        return "likely_not_fixed"
    if posterior <= config.FIXED_AT:
        return "verified_fixed"
    return "cannot_tell"


def is_uncertain(posterior: float) -> bool:
    return config.FIXED_AT < posterior < config.NOT_FIXED_AT
