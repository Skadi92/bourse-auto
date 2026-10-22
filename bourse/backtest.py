"""Backtest long uniquement : le signal de la clôture J est exécuté à l'ouverture de J+1."""

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .frais import ModeleFrais
from .signals import ACHAT, VENTE


@dataclass
class Resultat:
    debut: pd.Timestamp
    fin: pd.Timestamp
    perf_strategie: float
    perf_achat_conservation: float
    cagr_strategie: float
    cagr_achat_conservation: float
    drawdown_max_strategie: float
    drawdown_max_achat_conservation: float
    nb_trades: int
    taux_reussite: float
    exposition: float
    frais_total: float  # en €, pour des achats de `montant` € à chaque signal


def _cagr(courbe: pd.Series) -> float:
    annees = (courbe.index[-1] - courbe.index[0]).days / 365.25
    return courbe.iloc[-1] ** (1 / annees) - 1 if annees > 0 else float("nan")


def _drawdown_max(courbe: pd.Series) -> float:
    return float((courbe / courbe.cummax() - 1).min())


def executer(df: pd.DataFrame, frais: ModeleFrais | None = None,
             montant: float = 2000.0) -> tuple[Resultat, pd.DataFrame]:
    """df doit contenir Open, Close et la colonne signal produite par signals.evaluer.

    Chaque achat porte sur `montant` € ; la vente porte sur la valeur atteinte par la ligne,
    ce qui détermine la tranche de courtage. Sans modèle de frais, les coûts sont nuls.
    """
    taux = frais.taux if frais else (lambda _m, _a: 0.0)
    o, c, sig = df["Open"].to_numpy(), df["Close"].to_numpy(), df["signal"].to_numpy()
    n = len(df)
    rendement = np.zeros(n)
    position = np.zeros(n, dtype=int)
    en_position, prix_entree, trades = False, 0.0, []
    f_achat, frais_total = 0.0, 0.0

    for t in range(1, n):
        ordre = sig[t - 1]
        if not en_position and ordre == ACHAT:
            en_position, prix_entree = True, o[t]
            f_achat = taux(montant, True)
            frais_total += montant * f_achat
            rendement[t] = (c[t] / o[t]) * (1 - f_achat) - 1
        elif en_position and ordre == VENTE:
            en_position = False
            valeur = montant * (1 - f_achat) * o[t] / prix_entree
            f_vente = taux(valeur, False)
            frais_total += valeur * f_vente
            rendement[t] = (o[t] / c[t - 1]) * (1 - f_vente) - 1
            trades.append(valeur * (1 - f_vente) / montant - 1)
        elif en_position:
            rendement[t] = c[t] / c[t - 1] - 1
        position[t] = int(en_position)

    if en_position:  # position encore ouverte : valorisée à la dernière clôture
        trades.append(c[-1] / prix_entree * (1 - f_achat) - 1)

    courbe = pd.Series(np.cumprod(1 + rendement), index=df.index)
    # Achat-conservation : un seul achat de `montant` €, frais d'entrée compris.
    bh = df["Close"] / df["Close"].iloc[0] * (1 - taux(montant, True))
    res = Resultat(
        debut=df.index[0],
        fin=df.index[-1],
        perf_strategie=courbe.iloc[-1] - 1,
        perf_achat_conservation=bh.iloc[-1] - 1,
        cagr_strategie=_cagr(courbe),
        cagr_achat_conservation=_cagr(bh),
        drawdown_max_strategie=_drawdown_max(courbe),
        drawdown_max_achat_conservation=_drawdown_max(bh),
        nb_trades=len(trades),
        taux_reussite=float(np.mean([t > 0 for t in trades])) if trades else float("nan"),
        exposition=float(position.mean()),
        frais_total=frais_total,
    )
    detail = pd.DataFrame({"position": position, "courbe": courbe, "achat_conservation": bh})
    return res, detail
