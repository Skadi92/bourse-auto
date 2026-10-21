import tomllib
from pathlib import Path

import numpy as np
import pandas as pd

from bourse import backtest, indicators, signals

CFG = tomllib.loads((Path(__file__).resolve().parent.parent / "config.toml").read_text(encoding="utf-8"))


def ohlc(close: np.ndarray) -> pd.DataFrame:
    idx = pd.bdate_range("2020-01-01", periods=len(close))
    close = pd.Series(close, index=idx)
    return pd.DataFrame({
        "Open": close.shift(1).fillna(close.iloc[0]),
        "High": close * 1.005,
        "Low": close * 0.995,
        "Close": close,
        "Volume": 1_000,
    })


def evaluer(close: np.ndarray) -> pd.DataFrame:
    return signals.evaluer(indicators.calculer(ohlc(close), CFG["indicateurs"]), CFG["regles"])


def test_tendance_haussiere_detectee():
    df = evaluer(100 * 1.003 ** np.arange(300))
    assert df["etat"].iloc[-1] == signals.HAUSSE
    assert (df["sar"].iloc[-50:] < df["Close"].iloc[-50:]).all()


def test_tendance_baissiere_detectee():
    # Baisse dont la pente absolue s'accentue : sur une baisse à taux constant, le MACD
    # (exprimé en valeur absolue) rétrécit avec le prix et l'histogramme devient positif.
    t = np.arange(300)
    df = evaluer(200 - 0.001 * t**2)
    assert df["etat"].iloc[-1] == signals.BAISSE


def test_retournement_haussier_et_signal_achat():
    baisse = 100 * 0.995 ** np.arange(150)
    hausse = baisse[-1] * 1.006 ** np.arange(1, 100)
    df = evaluer(np.concatenate([baisse, hausse]))
    apres = df.iloc[150:]
    assert (apres["etat"] == signals.RETOURNEMENT_HAUSSIER).any()
    assert (apres["signal"] == signals.ACHAT).any()


def test_stabilite_sur_marche_plat():
    rng = np.random.default_rng(0)
    bruit = np.concatenate([rng.normal(0, 0.02, 200), rng.normal(0, 0.002, 100)])
    df = evaluer(100 * np.exp(np.cumsum(bruit) * 0.1))
    assert (df["etat"].iloc[-30:] == signals.STABILITE).any()


def test_backtest_sans_biais_d_anticipation():
    """Un signal à la clôture J n'affecte la position qu'à partir de J+1."""
    df = ohlc(np.linspace(100, 120, 10))
    df["signal"] = ""
    df.iloc[3, df.columns.get_loc("signal")] = signals.ACHAT
    _, detail = backtest.executer(df, frais_bps=0)
    assert detail["position"].iloc[3] == 0
    assert detail["position"].iloc[4] == 1
