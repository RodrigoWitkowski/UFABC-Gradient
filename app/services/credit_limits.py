from decimal import ROUND_CEILING, Decimal


def calculate_max_quarter_credits(ca: Decimal | None) -> Decimal | None:
    if ca is None:
        return None
    return (Decimal(20) + (Decimal(2) * ca)).to_integral_value(rounding=ROUND_CEILING)
