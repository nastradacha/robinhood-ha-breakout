"""Option math utilities (Black–Scholes).

Currently only supports delta calculation for calls/puts and assumes
continuous compounding, European style, risk-free rate r, time to
expiration T (in years), volatility sigma, underlying price S, strike K.

This lightweight helper avoids external dependencies beyond NumPy / SciPy.
SciPy is not a hard requirement because we only need the standard normal
CDF, which NumPy provides via `math.erf` approximation.
"""
from __future__ import annotations

import math
from typing import Literal


SQRT_2PI = math.sqrt(2.0 * math.pi)


def _phi(x: float) -> float:
    """Standard normal PDF."""
    return math.exp(-0.5 * x * x) / SQRT_2PI


def _Phi(x: float) -> float:
    """Standard normal CDF using error function for speed."""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def black_scholes_delta(
    S: float,
    K: float,
    T: float,
    sigma: float,
    r: float = 0.0,
    option_type: Literal["call", "put"] = "call",
) -> float:
    """Return the Black-Scholes delta for an option.

    Args:
        S: Underlying price.
        K: Strike price.
        T: Time to expiration in *years* (e.g. 7/365).
        sigma: Volatility (implied), expressed as decimal (e.g. 0.25).
        r: Risk-free rate (annualised, decimal). We default to 0 as per
           spec for intraday 0DTE.
        option_type: "call" or "put".
    """
    if T <= 0 or sigma <= 0 or S <= 0 or K <= 0:
        return 0.0

    d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))

    if option_type == "call":
        return _Phi(d1)
    else:
        # Put delta = Phi(d1) - 1
        return _Phi(d1) - 1.0
