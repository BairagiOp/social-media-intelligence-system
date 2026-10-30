"""pandas version compatibility helpers.

pandas 3.0 stores string columns with dtype ``str`` instead of ``object``,
so ``series.dtype == object`` no longer identifies text columns. Use
:func:`is_text_series` everywhere text columns must be detected.
"""
from __future__ import annotations

import pandas as pd


def is_text_series(series: pd.Series) -> bool:
    """True when a Series holds text (object dtype in pandas 2, str dtype in 3)."""
    dtype = series.dtype
    if dtype == object:
        return True
    try:
        return bool(pd.api.types.is_string_dtype(dtype))
    except (TypeError, ValueError, NotImplementedError):  # pragma: no cover
        return False
