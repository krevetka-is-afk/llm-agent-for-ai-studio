from dataclasses import dataclass
import re

from engine_skill import EngineCard, EngineSkillRegistry


@dataclass(frozen=True)
class RouteDecision:
    skill_id: str
    reason: str


class PrimaryConsultant:
    def __init__(
        self,
        skill_registry: EngineSkillRegistry,
        fallback_skill_id: str,
    ):
        self._skill_registry = skill_registry
        self._fallback_skill_id = fallback_skill_id
        self._skill_registry.require(fallback_skill_id)

    def route(self, input_user_message: str) -> RouteDecision:
        cards = self._skill_registry.cards
        if len(cards) == 1:
            card = cards[0]
            return RouteDecision(
                skill_id=card.skill_id,
                reason="Only registered skill is available.",
            )

        message_terms = _terms(input_user_message)
        scored_cards = [
            (_score_card(message_terms, card), card)
            for card in cards
        ]
        scored_cards.sort(key=lambda item: item[0], reverse=True)

        best_score, best_card = scored_cards[0]
        if best_score > 0:
            return RouteDecision(
                skill_id=best_card.skill_id,
                reason=f"Matched request terms to {best_card.skill_id} skill card.",
            )

        fallback_card = self._skill_registry.require(self._fallback_skill_id).card
        return RouteDecision(
            skill_id=fallback_card.skill_id,
            reason="No specific skill matched; using fallback skill.",
        )


def _score_card(message_terms: set[str], card: EngineCard) -> int:
    searchable_text = " ".join(
        (
            card.skill_id,
            card.name,
            card.description,
            " ".join(card.tags),
            " ".join(card.examples),
            " ".join(card.tools),
        )
    )
    card_terms = _terms(searchable_text)
    return len(message_terms & card_terms)


def _terms(value: str) -> set[str]:
    return {
        term
        for term in re.findall(r"[\w-]+", value.lower())
        if len(term) >= 3
    }
