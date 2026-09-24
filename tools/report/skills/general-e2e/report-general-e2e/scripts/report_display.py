"""Display-only decimal rounding consistent with Excel numeric formats."""

from decimal import Decimal, ROUND_HALF_UP, localcontext


def fixed_number(value, digits=2, *, grouping=False, multiplier=1):
    number = Decimal(str(value)) * multiplier
    with localcontext() as context:
        context.prec = max(28, number.adjusted() + digits + 2)
        rounded = number.quantize(Decimal(1).scaleb(-digits), rounding=ROUND_HALF_UP)
    return format(rounded, f"{',' if grouping else ''}.{digits}f")
