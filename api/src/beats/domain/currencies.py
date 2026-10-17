"""The currencies a client can be billed in, and their minor units.

A hand-kept table of the circulating ISO 4217 codes (List One), as of
October 2026. It is the one source of a currency's minor units: the browser's
ICU data disagrees with ISO on some codes, HUF and IQD among them, so every
money figure the API sends carries `minor_units` beside `currency`, read from
here, and the SPA never asks `Intl` how many digits a currency has.

Left out on purpose: the fund codes (BOV, CHE, CHW, CLF, COU, MXV, USN,
UYI, UYW), the precious metals and SDR-like units (XAG, XAU, XDR, XPD, XPT,
XSU, XUA, the XB* bond units) and the testing codes (XTS, XXX). Nobody bills
an hour in them.

A code that leaves circulation moves from `_ACTIVE` to `_WITHDRAWN`, never
out of the module: a new client cannot pick it, and a client already priced
in it still reads, with the same minor units.
"""

from functools import cache
from typing import NamedTuple

from beats.domain.exceptions import UnknownCurrency

_ZERO = "BIF CLP DJF GNF ISK JPY KMF KRW PYG RWF UGX VND VUV XAF XOF XPF"
_THREE = "BHD IQD JOD KWD LYD OMR TND"
_TWO = """
    AED AFN ALL AMD AOA ARS AUD AWG AZN
    BAM BBD BDT BMD BND BOB BRL BSD BTN BWP BYN BZD
    CAD CDF CHF CNY COP CRC CUP CVE CZK
    DKK DOP DZD
    EGP ERN ETB EUR
    FJD FKP
    GBP GEL GHS GIP GMD GTQ GYD
    HKD HNL HTG HUF
    IDR ILS INR IRR
    JMD
    KES KGS KHR KPW KYD KZT
    LAK LBP LKR LRD LSL
    MAD MDL MGA MKD MMK MNT MOP MRU MUR MVR MWK MXN MYR MZN
    NAD NGN NIO NOK NPR NZD
    PAB PEN PGK PHP PKR PLN
    QAR
    RON RSD RUB
    SAR SBD SCR SDG SEK SGD SHP SLE SOS SRD SSP STN SVC SYP SZL
    THB TJS TMT TOP TRY TTD TWD TZS
    UAH USD UYU UZS
    VED VES
    WST
    XCD XCG
    YER
    ZAR ZMW ZWG
"""

_ACTIVE: dict[str, int] = {
    code: units for units, codes in ((0, _ZERO), (2, _TWO), (3, _THREE)) for code in codes.split()
}

# Out of circulation since this table was first kept: Curaçao and Sint
# Maarten's guilder for the Caribbean guilder (XCG) in 2025, Bulgaria's lev
# for the euro on 1 January 2026.
_WITHDRAWN: dict[str, int] = {"ANG": 2, "BGN": 2}


class Currency(NamedTuple):
    code: str
    minor_units: int


def check_currency(code: str) -> None:
    """Raise `UnknownCurrency` unless `code` is one a client may be billed in now."""
    if code not in _ACTIVE:
        raise UnknownCurrency(code)


def minor_units(code: str) -> int:
    """The digits after the decimal point in `code`'s amounts: 2 for EUR, 0
    for JPY, 3 for KWD. A withdrawn code still answers, for the clients
    already priced in it."""
    units = _ACTIVE.get(code, _WITHDRAWN.get(code))
    if units is None:
        raise UnknownCurrency(code)
    return units


@cache
def currencies() -> list[Currency]:
    """Every code a client may pick, by code. Cached: the table is static."""
    return [Currency(code, units) for code, units in sorted(_ACTIVE.items())]
