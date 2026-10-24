"""Evidence fusion: logit(posterior) = logit(prior) + sum(ln(LR_i)).

Independence between checks is an approximation. Correlated pairs (photo + citizen)
are down-weighted: the weaker contribution is scaled by CORRELATION_WEIGHT.
"""
import math
from . import config
from .models import Evidence


def _clip(p: float, eps: float = 1e-6) -> float:
    return min(max(p, eps), 1 - eps)


def logit(p: float) -> float:
    p = _clip(p)
    return math.log(p / (1 - p))


def sigmoid(x: float) -> float:
    return 1 / (1 + math.exp(-x))


def fuse(prior: float, evidence: list[Evidence]) -> float:
    contrib: dict[str, float] = {}
    for e in evidence:
        # repeated checks of the same type: keep the latest only
        contrib[e.check] = math.log(e.likelihood_ratio)
    for pair in config.CORRELATED_PAIRS:
        if pair <= contrib.keys():
            weaker = min(pair, key=lambda c: abs(contrib[c]))
            contrib[weaker] *= config.CORRELATION_WEIGHT
    return sigmoid(logit(prior) + sum(contrib.values()))


def state_for(posterior: float) -> str:
    if posterior >= config.THRESH_NOT_FIXED:
        return "likely_not_fixed"
    if posterior <= config.THRESH_FIXED:
        return "verified_fixed"
    return "cannot_tell"


def is_uncertain(posterior: float) -> bool:
    return config.THRESH_FIXED < posterior < config.THRESH_NOT_FIXED
