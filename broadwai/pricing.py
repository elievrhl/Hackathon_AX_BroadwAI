"""Indicative standard USD rates checked 2026-09-26; not a supplier invoice."""

RATES = {
    "gpt-5.4-mini": (0.75, 0.075, 4.50),
    "gpt-5.4-nano": (0.20, 0.02, 1.25),
}


def estimate_cost(calls, web_calls=0):
    amount = web_calls * 0.01
    unknown = []
    for call in calls:
        rates = RATES.get(call["model"])
        usage = call.get("usage")
        if not rates or not usage:
            unknown.append(call["model"])
            continue
        cached = usage.get("cached_input_tokens") or 0
        amount += (
            (usage["input_tokens"] - cached) * rates[0]
            + cached * rates[1]
            + usage["output_tokens"] * rates[2]
        ) / 1_000_000
    return {
        "estimated_usd": round(amount, 6) if not unknown else None,
        "known_subtotal_usd": round(amount, 6),
        "unpriced_calls": len(unknown),
        "rates_date": "2026-09-26",
        "basis": "Tokens déclarés et outils web ; tarif standard, hors taxes et suppléments.",
    }
