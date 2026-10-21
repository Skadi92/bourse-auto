"""Calcul des indicateurs techniques à partir d'un historique OHLC journalier."""

import numpy as np
import pandas as pd


def ema(serie: pd.Series, periode: int) -> pd.Series:
    return serie.ewm(span=periode, adjust=False).mean()


def wilder(serie: pd.Series, periode: int) -> pd.Series:
    """Lissage de Wilder (utilisé par l'ADX)."""
    return serie.ewm(alpha=1 / periode, adjust=False).mean()


def macd(close: pd.Series, rapide: int, lente: int, signal: int) -> pd.DataFrame:
    ligne = ema(close, rapide) - ema(close, lente)
    sig = ema(ligne, signal)
    return pd.DataFrame({"macd": ligne, "macd_signal": sig, "macd_hist": ligne - sig})


def bollinger(close: pd.Series, periode: int, ecarts: float) -> pd.DataFrame:
    milieu = close.rolling(periode).mean()
    ecart = close.rolling(periode).std(ddof=0)
    haute = milieu + ecarts * ecart
    basse = milieu - ecarts * ecart
    return pd.DataFrame(
        {
            "bb_milieu": milieu,
            "bb_haute": haute,
            "bb_basse": basse,
            "bb_largeur": (haute - basse) / milieu,
            "bb_pct": (close - basse) / (haute - basse),
        }
    )


def parabolic_sar(high: pd.Series, low: pd.Series, pas: float, maximum: float) -> pd.DataFrame:
    """SAR parabolique de Wilder. Renvoie le SAR et la tendance (+1 haussière, -1 baissière)."""
    h, l = high.to_numpy(float), low.to_numpy(float)
    n = len(h)
    sar = np.full(n, np.nan)
    tendance = np.zeros(n, dtype=int)
    if n < 2:
        return pd.DataFrame({"sar": sar, "sar_tendance": tendance}, index=high.index)

    haussier = h[1] >= h[0]
    ep = h[1] if haussier else l[1]
    sar[1] = l[0] if haussier else h[0]
    af = pas
    tendance[1] = 1 if haussier else -1

    for i in range(2, n):
        prec = sar[i - 1] + af * (ep - sar[i - 1])
        if haussier:
            prec = min(prec, l[i - 1], l[i - 2])
            if l[i] < prec:
                haussier, prec, ep, af = False, ep, l[i], pas
            elif h[i] > ep:
                ep, af = h[i], min(af + pas, maximum)
        else:
            prec = max(prec, h[i - 1], h[i - 2])
            if h[i] > prec:
                haussier, prec, ep, af = True, ep, h[i], pas
            elif l[i] < ep:
                ep, af = l[i], min(af + pas, maximum)
        sar[i] = prec
        tendance[i] = 1 if haussier else -1

    return pd.DataFrame({"sar": sar, "sar_tendance": tendance}, index=high.index)


def momentum(close: pd.Series, periode: int) -> pd.Series:
    """Momentum exprimé en taux de variation (%) sur la période."""
    return close.pct_change(periode) * 100


def adx(high: pd.Series, low: pd.Series, close: pd.Series, periode: int) -> pd.Series:
    hausse = high.diff()
    baisse = -low.diff()
    dm_plus = pd.Series(np.where((hausse > baisse) & (hausse > 0), hausse, 0.0), index=high.index)
    dm_moins = pd.Series(np.where((baisse > hausse) & (baisse > 0), baisse, 0.0), index=high.index)
    tr = pd.concat(
        [high - low, (high - close.shift()).abs(), (low - close.shift()).abs()], axis=1
    ).max(axis=1)
    atr = wilder(tr, periode)
    di_plus = 100 * wilder(dm_plus, periode) / atr
    di_moins = 100 * wilder(dm_moins, periode) / atr
    dx = 100 * (di_plus - di_moins).abs() / (di_plus + di_moins).replace(0, np.nan)
    return wilder(dx.fillna(0), periode)


def calculer(df: pd.DataFrame, p: dict) -> pd.DataFrame:
    """Ajoute tous les indicateurs au DataFrame OHLC (colonnes Open, High, Low, Close)."""
    out = df.copy()
    out = out.join(macd(df["Close"], p["macd_rapide"], p["macd_lente"], p["macd_signal"]))
    out = out.join(bollinger(df["Close"], p["bollinger_periode"], p["bollinger_ecarts"]))
    out = out.join(parabolic_sar(df["High"], df["Low"], p["sar_pas"], p["sar_max"]))
    out["momentum"] = momentum(df["Close"], p["momentum_periode"])
    out["adx"] = adx(df["High"], df["Low"], df["Close"], p["adx_periode"])
    return out
