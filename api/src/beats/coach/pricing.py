"""The coach's price table: USD per million tokens, by model.

Its own module, apart from the gateway, because two deployments read it: the
public API bills every call with it (`coach/gateway.py`), and the operator's
Capacity page says what the prompt cache saved with it — and the operator
root never imports `beats.settings`, which the gateway does
(docs/backoffice.md § Architecture).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ModelPricing:
    """USD per million tokens for one model.

    ``input`` and ``output`` are published list prices. Cache rates follow
    Anthropic's standard multipliers — a write costs 1.25x input, a read
    0.10x — but are stored rather than derived so a model that prices its
    cache differently can say so.
    """

    input: float
    output: float
    cache_write: float
    cache_read: float

    @classmethod
    def standard(cls, input_rate: float, output_rate: float) -> ModelPricing:
        return cls(input_rate, output_rate, input_rate * 1.25, input_rate * 0.10)


MODEL_PRICING: dict[str, ModelPricing] = {
    "claude-fable-5-1": ModelPricing.standard(10.0, 50.0),
    "claude-opus-5-5": ModelPricing.standard(4.0, 20.0),
    "claude-opus-5": ModelPricing.standard(5.0, 25.0),
    "claude-opus-4-8": ModelPricing.standard(5.0, 25.0),
    "claude-opus-4-7": ModelPricing.standard(5.0, 25.0),
    "claude-sonnet-5-5": ModelPricing.standard(2.0, 10.0),
    "claude-sonnet-5": ModelPricing.standard(2.0, 10.0),
    "claude-sonnet-4-6": ModelPricing.standard(3.0, 15.0),
    "claude-haiku-4-5": ModelPricing.standard(1.0, 5.0),
}

# An unrecognised model bills at the most expensive rate in the table. The
# budget ceiling is the reason: over-estimating a new model stops the coach
# early and visibly, where under-estimating would let it spend past the cap
# with nothing to show it had happened.
UNKNOWN_MODEL_PRICING = ModelPricing.standard(
    max(p.input for p in MODEL_PRICING.values()),
    max(p.output for p in MODEL_PRICING.values()),
)


def pricing_for(model: str) -> ModelPricing:
    """Resolve a model id to its rates, tolerating dated suffixes.

    The longest known prefix wins: `claude-opus-5-5-20261001` is Opus 5.5,
    not Opus 5, whose id is a prefix of it and which bills more.
    """
    exact = MODEL_PRICING.get(model)
    if exact is not None:
        return exact
    for known in sorted(MODEL_PRICING, key=len, reverse=True):
        if model.startswith(known):
            return MODEL_PRICING[known]
    logger.warning("No pricing for model %s; billing at the highest known rate", model)
    return UNKNOWN_MODEL_PRICING


def cache_saving_usd(model: str, cache_read: int, cache_write: int) -> float:
    """What the prompt cache saved on one model's tokens, against sending the
    same tokens uncached: each read billed at the read rate instead of input,
    less the premium each write paid over input. Negative when the writes
    cost more than the reads saved."""
    rates = pricing_for(model)
    saved = cache_read * (rates.input - rates.cache_read)
    premium = cache_write * (rates.cache_write - rates.input)
    return (saved - premium) / 1_000_000
