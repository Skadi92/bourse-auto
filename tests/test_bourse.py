import tomllib
from pathlib import Path

import numpy as np
import pandas as pd

from bourse import backtest, indicators, signals

CFG = tomllib.loads((Path(__file__).resolve().parent.parent / "config.toml").read_text(encoding="utf-8"))


def ohlc(close: np.ndarray) -> pd.DataFrame:
    idx = pd.bdate_range("2015-01-01", periods=len(close))
    close = pd.Series(close, index=idx)
    return pd.DataFrame({
        "Open": close.shift(1).fillna(close.iloc[0]),
        "High": close * 1.005,
        "Low": close * 0.995,
        "Close": close,
        "Volume": 1_000,
    })


def evaluer(close: np.ndarray) -> pd.DataFrame:
    df = indicators.calculer(ohlc(close), CFG["indicateurs"], CFG["fond"])
    return signals.regime(signals.evaluer(df, CFG["regles"]), CFG["regles_fond"])


def bruit(n: int, vol: float, graine: int = 0) -> np.ndarray:
    return np.random.default_rng(graine).normal(0, vol, n)


# --- État court terme (descriptif) ---

def test_tendance_haussiere_detectee():
    df = evaluer(100 * 1.003 ** np.arange(300))
    assert df["etat"].iloc[-1] == signals.HAUSSE


def test_tendance_baissiere_detectee():
    # Baisse dont la pente absolue s'accentue : sur une baisse à taux constant, le MACD
    # (exprimé en valeur absolue) rétrécit avec le prix et l'histogramme devient positif.
    t = np.arange(300)
    df = evaluer(200 - 0.001 * t**2)
    assert df["etat"].iloc[-1] == signals.BAISSE


def test_stabilite_sur_marche_plat():
    b = np.concatenate([bruit(200, 0.02), bruit(100, 0.002)])
    df = evaluer(100 * np.exp(np.cumsum(b) * 0.1))
    assert (df["etat"].iloc[-30:] == signals.STABILITE).any()


# --- Régime de fond et signaux ---

def test_hausse_durable_un_seul_achat():
    rendements = 0.0012 + bruit(800, 0.006)
    df = evaluer(100 * np.exp(np.cumsum(rendements)))
    assert (df["signal"] == signals.ACHAT).sum() == 1
    assert df["regime"].iloc[-1] == signals.HAUSSE


def test_krach_declenche_vente_rapide():
    hausse = 0.0006 + bruit(600, 0.01)
    krach = np.full(15, -0.025)
    df = evaluer(100 * np.exp(np.cumsum(np.concatenate([hausse, krach]))))
    ventes = df.iloc[600:][df["signal"].iloc[600:] == signals.VENTE]
    assert len(ventes) == 1 and ventes["motif"].iloc[0] == "krach"


def test_marche_sans_tendance_peu_de_signaux():
    df = evaluer(100 * np.exp(np.cumsum(bruit(1500, 0.012, graine=3))))
    annees = len(df) / 252
    assert (df["signal"] != "").sum() / annees < 2


def test_force_bornee():
    df = evaluer(100 * np.exp(np.cumsum(0.0006 + bruit(800, 0.01))))
    assert df["force"].between(0, 100).all()


def test_backtest_sans_biais_d_anticipation():
    """Un signal à la clôture J n'affecte la position qu'à partir de J+1."""
    df = ohlc(np.linspace(100, 120, 10))
    df["signal"] = ""
    df.iloc[3, df.columns.get_loc("signal")] = signals.ACHAT
    _, detail = backtest.executer(df, frais_bps=0)
    assert detail["position"].iloc[3] == 0
    assert detail["position"].iloc[4] == 1
