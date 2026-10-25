"""USD per million tokens for the cost estimate in llm_calls and the daily spend cap. A model without a price is
never called (the cap could not be enforced)."""

# input, output, cache read, 5-minute cache write
PRICES: dict[str, tuple[float, float, float, float]] = {
    "claude-haiku-5-5": (0.10, 0.50, 0.01, 0.125),
    "claude-sonnet-5-5": (2.00, 10.00, 0.20, 2.50),
    "claude-opus-5-5": (4.00, 20.00, 0.20, 5.00),
}


def has_price(model: str) -> bool:
    return model in PRICES


def estimate_cost(
    model: str, input_tokens: int, output_tokens: int, cache_read: int = 0, cache_write: int = 0
) -> float:
    """Anthropic usage: input_tokens excludes the cached tokens."""
    p_in, p_out, p_read, p_write = PRICES[model]
    return round(
        (input_tokens * p_in + output_tokens * p_out + cache_read * p_read + cache_write * p_write) / 1_000_000, 6
    )
