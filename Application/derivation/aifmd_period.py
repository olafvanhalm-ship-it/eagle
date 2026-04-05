"""AIF reporting period derivation.

Derives AIF reporting period type, start date, and end date when not explicitly
specified, based on the AIFM's period and the fund's inception date.
"""

# Ensure shared module can be imported from parent directory
import sys
from pathlib import Path as _Path
_app_root = _Path(__file__).resolve().parent.parent.parent
if str(_app_root) not in sys.path:
    sys.path.insert(0, str(_app_root))

from shared.formatting import _reporting_period_dates


def _derive_aif_period(aifm_period_type: str, year: int,
                        inception_date_str: str | None) -> tuple[str, str, str]:
    """Derive AIF reporting period type, start date, and end date.

    When an AIF has no explicit Reporting Period Type in the template, it
    inherits the AIFM's period.  However, if the fund's inception date falls
    *within* the AIFM period, reporting starts from the first day of the
    next quarter after inception.  The period type is then adjusted to
    match the resulting quarter range.

    Rules:
    - New fund reports from 1st day of the next quarter after inception.
    - Period type is derived from (start_quarter … end_quarter):
        Q-start to Q4  → Y1 (4q), X2 (3q), H2 (2q), Q4 (1q)
        Q-start to Q2  → H1 (2q), Q2 (1q)
        Q-start to Q3  → X1 (3q, only for terminated funds), Q3 (1q)
        Q-start to Q1  → Q1 (1q)
    - X1 is only used for terminated funds, not new ones.

    Returns (period_type, start_date, end_date).
    """
    # Standard period dates from AIFM
    std_start, std_end = _reporting_period_dates(aifm_period_type, year)

    if not inception_date_str:
        return aifm_period_type, std_start, std_end

    # Parse inception date
    from datetime import date
    try:
        if isinstance(inception_date_str, str):
            inc = date.fromisoformat(inception_date_str[:10])
        else:
            inc = inception_date_str
    except (ValueError, TypeError):
        return aifm_period_type, std_start, std_end

    period_start = date.fromisoformat(std_start)
    period_end = date.fromisoformat(std_end)

    # If inception is before (or on) the period start, fund existed already
    if inc <= period_start:
        return aifm_period_type, std_start, std_end

    # If inception is after the period end, fund doesn't report this period
    if inc > period_end:
        return aifm_period_type, std_start, std_end

    # Fund is new: determine next quarter start after inception
    # Quarter starts: Q1=Jan1, Q2=Apr1, Q3=Jul1, Q4=Oct1
    q_starts = [
        (1, date(year, 1, 1)),
        (2, date(year, 4, 1)),
        (3, date(year, 7, 1)),
        (4, date(year, 10, 1)),
    ]
    # Find the first quarter start that is strictly after inception
    aif_start = None
    start_q = None
    for q_num, q_date in q_starts:
        if q_date > inc:
            aif_start = q_date
            start_q = q_num
            break
    if aif_start is None or aif_start > period_end:
        # Inception in Q4 and no next quarter in this year —
        # or next quarter is beyond the period
        return aifm_period_type, std_start, std_end

    # Determine end quarter number
    end_month = period_end.month
    end_q = (end_month - 1) // 3 + 1  # 1-4

    # Map (start_q, end_q) → period_type
    # Number of quarters covered
    num_q = end_q - start_q + 1
    if end_q == 4:
        # ends in Q4
        period_map = {4: "Y1", 3: "X2", 2: "H2", 1: "Q4"}
    elif end_q == 2:
        # ends in Q2
        period_map = {2: "H1", 1: "Q2"}
    elif end_q == 3:
        # ends in Q3 — X1 is only for terminated funds, so use Q3 for single quarter
        period_map = {3: "X1", 2: "H2" if start_q == 2 else "Q3", 1: "Q3"}
        # Actually for new funds ending Q3, the combinations are:
        # Q1-Q3 = X1 (but X1 is only for terminated funds)
        # Q2-Q3 = no standard code, shouldn't happen in practice
        # Q3 only = Q3
        period_map = {1: "Q3"}
    elif end_q == 1:
        period_map = {1: "Q1"}
    else:
        period_map = {1: f"Q{end_q}"}

    derived_type = period_map.get(num_q, aifm_period_type)
    aif_start_str = aif_start.isoformat()

    return derived_type, aif_start_str, std_end
