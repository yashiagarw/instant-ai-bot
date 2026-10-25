"""Live LLM layer: extraction of symptoms and answers from free text, and question phrasing (see README).

Every step has a non-LLM fallback and runs only when LLM_PROVIDER=anthropic and ANTHROPIC_API_KEY are set.
Facts (prices, part fit, safety rules, which question to ask) never come from the model.
"""
