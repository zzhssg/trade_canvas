from __future__ import annotations

from dataclasses import dataclass

from trade_oracle.models import BaziSnapshot, FactorScore

STEM_ELEMENT = {
    "甲": "wood",
    "乙": "wood",
    "丙": "fire",
    "丁": "fire",
    "戊": "earth",
    "己": "earth",
    "庚": "metal",
    "辛": "metal",
    "壬": "water",
    "癸": "water",
}

BRANCH_ELEMENT = {
    "子": "water",
    "丑": "earth",
    "寅": "wood",
    "卯": "wood",
    "辰": "earth",
    "巳": "fire",
    "午": "fire",
    "未": "earth",
    "申": "metal",
    "酉": "metal",
    "戌": "earth",
    "亥": "water",
}

GENERATE = {
    "wood": "fire",
    "fire": "earth",
    "earth": "metal",
    "metal": "water",
    "water": "wood",
}

CONTROL = {
    "wood": "earth",
    "earth": "water",
    "water": "fire",
    "fire": "metal",
    "metal": "wood",
}


@dataclass(frozen=True)
class FactorBundle:
    scores: list[FactorScore]

    @property
    def total(self) -> float:
        return sum(it.score for it in self.scores)


def _element_strength(snapshot: BaziSnapshot) -> dict[str, int]:
    acc = {"wood": 0, "fire": 0, "earth": 0, "metal": 0, "water": 0}
    for p in (snapshot.year, snapshot.month, snapshot.day, snapshot.hour):
        acc[STEM_ELEMENT.get(p.stem, "earth")] += 1
        acc[BRANCH_ELEMENT.get(p.branch, "earth")] += 1
    return acc


def _relation_score(day_master: str, transit_elem: str) -> float:
    if day_master == transit_elem:
        return 1.0
    if GENERATE.get(day_master) == transit_elem:
        return 0.8
    if GENERATE.get(transit_elem) == day_master:
        return 0.5
    if CONTROL.get(day_master) == transit_elem:
        return -0.9
    if CONTROL.get(transit_elem) == day_master:
        return -0.6
    return 0.0


def score_factors(*, natal: BaziSnapshot, transit: BaziSnapshot) -> FactorBundle:
    day_master = STEM_ELEMENT.get(natal.day.stem, "earth")
    transit_elements = [
        STEM_ELEMENT.get(transit.year.stem, "earth"),
        STEM_ELEMENT.get(transit.month.stem, "earth"),
        STEM_ELEMENT.get(transit.day.stem, "earth"),
    ]
    relation = sum(_relation_score(day_master, elem) for elem in transit_elements)

    natal_strength = _element_strength(natal)
    strongest_elem = max(natal_strength.items(), key=lambda x: x[1])[0]

    blind_score = relation
    blind_reason = f"日主={day_master}，流年/月/日作用分={relation:.2f}"

    pattern_bonus = 0.7 if strongest_elem == day_master else -0.3
    pattern_score = relation * 0.6 + pattern_bonus
    pattern_reason = f"原局最旺五行={strongest_elem}，格局修正={pattern_bonus:+.2f}"

    balance_penalty = abs(natal_strength.get(day_master, 0) - 2) * 0.3
    strength_score = relation - balance_penalty
    strength_reason = f"日主平衡惩罚={balance_penalty:.2f}"

    def direction(v: float) -> str:
        if v > 0.35:
            return "bullish"
        if v < -0.35:
            return "bearish"
        return "neutral"

    scores = [
        FactorScore(school="盲派", score=blind_score, direction=direction(blind_score), reason=blind_reason),
        FactorScore(school="格局派", score=pattern_score, direction=direction(pattern_score), reason=pattern_reason),
        FactorScore(school="旺衰派", score=strength_score, direction=direction(strength_score), reason=strength_reason),
    ]
    return FactorBundle(scores=scores)
