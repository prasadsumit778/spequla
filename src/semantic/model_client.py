"""The three model-touching stages, corpus/07 section 2: intent
classification (stage 1), semantic IR generation (stage 4), narration
(stage 11). Nothing else in the Ask pipeline calls a model -- "Nothing that
touches a number is a model call" (section 2).

This module is the connection point, and only the connection point, per an
explicit instruction: build the interface every other module in this sprint
codes against, but do not wire up a real vendor SDK or require an API key
yet. corpus/00 VERIFY[V-012] leaves the model vendor as an open question
("zero-retention terms currently on offer... Owner: Co-founder") --
identical in kind to the auth-provider and object-storage decisions earlier
in this project, both of which were left to the user rather than guessed.

Two implementations ship today:

  - StubModelClient: fixture-driven, not a real model at all. Encodes
    corpus/10's golden questions as pre-built (intent, IR) pairs so the
    REST of the Ask pipeline -- validation, compilation, admission gates,
    bridges, citations -- can be built and tested for real, against real
    data, without a live model call. This is what
    tests/eval/test_golden_questions.py runs against. It proves the
    deterministic 10 of 11 stages in corpus/07 section 2's table; it
    proves nothing about natural-language understanding, which is the
    one thing still missing.

  - AnthropicModelClient: the real integration point, intentionally left
    unconfigured (raises ModelNotConfigured). When a decision on vendor
    and API key lands, implementing its three methods against the
    Anthropic API is the entire remaining work -- nothing else in this
    sprint's code changes, because everything downstream only depends on
    the ModelClient protocol, never on a specific vendor's SDK.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class ModelNotConfigured(Exception):
    """Raised by AnthropicModelClient until a real API key and vendor
    integration are wired up. Named clearly rather than failing with an
    opaque import or connection error."""


@dataclass
class IntentClassification:
    intent: str
    confidence: float
    reason: str


class ModelClient(Protocol):
    """The connection point. Every stage that touches a model in
    corpus/07's eleven-stage pipeline goes through exactly these three
    methods, and nothing else in the Ask pipeline imports a model SDK
    directly."""

    def classify_intent(self, question: str) -> IntentClassification: ...

    def generate_ir(self, question: str, intent: str) -> dict: ...

    def narrate(self, template: str, computed_values: dict) -> str: ...


class StubModelClient:
    """Fixture-driven, for testing the deterministic pipeline without a
    live model. fixtures: {question_text: (intent, ir_dict_or_reason)} --
    for intent == 'unsupported', the second element is the specific refusal
    reason (a string, corpus/07 section 6's own named reason for that
    question) rather than an IR dict, since an unsupported question never
    reaches IR generation at all. narrate() never fabricates commentary --
    it renders computed_values into the supplied template only, since
    narration wording rules (corpus/03 section 9) are the analyst's job in
    pilot one, not this stub's."""

    def __init__(self, fixtures: dict[str, tuple[str, dict | str]]):
        self._fixtures = fixtures

    def classify_intent(self, question: str) -> IntentClassification:
        if question not in self._fixtures:
            return IntentClassification(intent="unsupported", confidence=0.0,
                                           reason="no fixture for this question -- stub client, not a real model")
        intent, payload = self._fixtures[question]
        reason = payload if intent == "unsupported" else "fixture"
        return IntentClassification(intent=intent, confidence=1.0, reason=reason)

    def generate_ir(self, question: str, intent: str) -> dict:
        if question not in self._fixtures:
            raise ModelNotConfigured(f"no fixture registered for {question!r}")
        fixture_intent, ir_dict = self._fixtures[question]
        if fixture_intent != intent:
            raise ModelNotConfigured(f"fixture intent {fixture_intent!r} does not match requested {intent!r}")
        return ir_dict

    def narrate(self, template: str, computed_values: dict) -> str:
        return template.format(**computed_values)


class AnthropicModelClient:
    """Real integration point. Deliberately not implemented yet -- see
    module docstring. Wiring this up means: read ANTHROPIC_API_KEY,
    construct an anthropic.Anthropic() client, call it for intent
    classification (small/fast model per corpus/07 section 9's routing
    table) and IR generation (strong model, constrained decoding against
    the IRRequest JSON schema, retried once on an invalid parse per
    corpus/07 section 2 stage 4, then surfaced as unsupported). Nothing
    else in src/semantic/ changes when this happens."""

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key

    def classify_intent(self, question: str) -> IntentClassification:
        raise ModelNotConfigured(
            "AnthropicModelClient is not wired up yet -- set ANTHROPIC_API_KEY and implement "
            "classify_intent against the Anthropic API. See src/semantic/model_client.py."
        )

    def generate_ir(self, question: str, intent: str) -> dict:
        raise ModelNotConfigured(
            "AnthropicModelClient is not wired up yet -- set ANTHROPIC_API_KEY and implement "
            "generate_ir against the Anthropic API. See src/semantic/model_client.py."
        )

    def narrate(self, template: str, computed_values: dict) -> str:
        raise ModelNotConfigured(
            "AnthropicModelClient is not wired up yet -- set ANTHROPIC_API_KEY and implement "
            "narrate against the Anthropic API. See src/semantic/model_client.py."
        )
