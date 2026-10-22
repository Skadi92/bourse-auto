"""Accès aux cours. Isolé ici pour pouvoir remplacer yfinance par une autre source."""

import sys
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


def _seances_horaires(ticker: str) -> pd.DataFrame:
    """Séances des cinq derniers jours reconstituées à partir des barres horaires."""
    h = yf.Ticker(ticker).history(period="5d", interval="1h", auto_adjust=True)
    if h is None or h.empty:
        return pd.DataFrame(columns=COLONNES)
    h = h[COLONNES].dropna(subset=["Open", "High", "Low", "Close"])
    jours = h.index.normalize()
    return h.groupby(jours).agg(
        {"Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"}
    )


def charger(ticker: str, periode: str) -> pd.DataFrame:
    """Historique journalier ajusté (dividendes et divisions) d'un ticker Yahoo Finance.

    Yahoo omet parfois une séance récente dans ses données journalières (constaté sur
    Euronext) : elle est alors reconstituée à partir des barres horaires. La séance du jour
    est écartée si elle n'est pas terminée, pour ne jamais calculer un signal intraday.
    """
    df = yf.Ticker(ticker).history(period=periode, interval="1d", auto_adjust=True)
    if df is None or df.empty:
        raise DonneesIndisponibles(f"aucune donnée renvoyée pour {ticker}")
    df = df[COLONNES].dropna(subset=["Open", "High", "Low", "Close"])

    try:
        horaires = _seances_horaires(ticker)
        manquantes = horaires.loc[horaires.index > df.index[-6]].index.difference(df.index)
        if len(manquantes):
            print(f"[INFO] {ticker} : séance(s) reconstituée(s) depuis les barres horaires : "
                  f"{', '.join(d.strftime('%Y-%m-%d') for d in manquantes)}", file=sys.stderr)
            df = pd.concat([df, horaires.loc[manquantes]]).sort_index()
    except Exception as e:  # la reconstitution est un complément, pas une condition
        print(f"[AVERTISSEMENT] {ticker} : contrôle des séances manquantes impossible : {e}",
              file=sys.stderr)

    tz = df.index.tz
    if tz is not None:
        maintenant = datetime.now(tz)
        cloture = HEURE_CLOTURE.get(str(tz), HEURE_CLOTURE_DEFAUT)
        if df.index[-1].date() == maintenant.date() and maintenant.time() < cloture:
            df = df.iloc[:-1]
        df.index = df.index.tz_localize(None)
    df.index = pd.to_datetime(df.index).normalize()
    return df
