"""Money helpers (issue #111 / review finding C3).

SQLite stores ``Numeric`` as REAL, so ``SUM(amount)`` comes back as a float and
the reporting code used ``Decimal(str(x))`` in ~18 places. Quantising to cents
absorbs the float-representation noise; the accumulated error from summing
2-decimal values in float stays many orders of magnitude below half a cent for
any realistic transaction count.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

CENTS = Decimal("0.01")


def money_from_db(value: object) -> Decimal:
    """Coerce a raw DB numeric/aggregate to a clean 2-decimal ``Decimal``."""
    if value is None:
        return Decimal("0.00")
    return Decimal(str(value)).quantize(CENTS, rounding=ROUND_HALF_UP)
