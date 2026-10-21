"""Accès aux cours. Isolé ici pour pouvoir remplacer yfinance par une autre source."""

from datetime import datetime, time

import pandas as pd
import yfinance as yf

COLONNES = ["Open", "High", "Low", "Close", "Volume"]
# Heure locale au-delà de laquelle la séance du jour est considérée close, avec une marge
# après la clôture officielle (Euronext et Xetra 17 h 30, Londres 16 h 30, New York 16 h).
HEURE_CLOTURE = {"America/New_York": time(16, 30), "Europe/London": time(17, 0)}
HEURE_CLOTURE_DEFAUT = time(18, 0)


class DonneesIndisponibles(Exception):
    pass


def charger(ticker: str, periode: str) -> pd.DataFrame:
    """Historique journalier ajusté (dividendes et divisions) d'un ticker Yahoo Finance.

    La bougie du jour est écartée si la séance n'est pas terminée, pour ne jamais
    calculer un signal sur un cours intraday.
    """
    df = yf.Ticker(ticker).history(period=periode, interval="1d", auto_adjust=True)
    if df is None or df.empty:
        raise DonneesIndisponibles(f"aucune donnée renvoyée pour {ticker}")
    df = df[COLONNES].dropna(subset=["Open", "High", "Low", "Close"])

    tz = df.index.tz
    if tz is not None:
        maintenant = datetime.now(tz)
        cloture = HEURE_CLOTURE.get(str(tz), HEURE_CLOTURE_DEFAUT)
        if df.index[-1].date() == maintenant.date() and maintenant.time() < cloture:
            df = df.iloc[:-1]
        df.index = df.index.tz_localize(None)
    df.index = pd.to_datetime(df.index).normalize()
    return df
