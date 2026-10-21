"""Moteur de règles : régime de marché, état et signaux ACHAT / VENTE.

Chaque indicateur vote dans un sens (+1 haussier, -1 baissier) :
- SAR parabolique : prix au-dessus ou en dessous du SAR ;
- MACD : ligne MACD au-dessus ou en dessous de sa ligne de signal ;
- momentum : variation positive ou négative sur la période ;
- Bollinger : clôture au-dessus ou en dessous de la bande médiane.
Le score directionnel est la somme des votes (de -4 à +4). L'ADX et la largeur des
bandes de Bollinger qualifient le régime (tendance ou marché stable).
"""

import numpy as np
import pandas as pd

HAUSSE = "HAUSSE"
BAISSE = "BAISSE"
RETOURNEMENT_HAUSSIER = "RETOURNEMENT_HAUSSIER"
RETOURNEMENT_BAISSIER = "RETOURNEMENT_BAISSIER"
STABILITE = "STABILITE"
NEUTRE = "NEUTRE"

ACHAT = "ACHAT"
VENTE = "VENTE"

LIBELLES = {
    HAUSSE: "Hausse confirmée",
    BAISSE: "Baisse confirmée",
    RETOURNEMENT_HAUSSIER: "Retournement haussier",
    RETOURNEMENT_BAISSIER: "Retournement baissier",
    STABILITE: "Stabilité (compression de volatilité)",
    NEUTRE: "Neutre, sans signal clair",
}


def _signe(serie: pd.Series) -> pd.Series:
    return np.sign(serie).fillna(0).astype(int)


def evaluer(df: pd.DataFrame, r: dict) -> pd.DataFrame:
    """Ajoute les votes, le score, l'état et les signaux à un DataFrame d'indicateurs."""
    out = df.copy()
    out["vote_sar"] = out["sar_tendance"].astype(int)
    out["vote_macd"] = _signe(out["macd_hist"])
    out["vote_momentum"] = _signe(out["momentum"])
    out["vote_bollinger"] = _signe(out["Close"] - out["bb_milieu"])
    votes = ["vote_sar", "vote_macd", "vote_momentum", "vote_bollinger"]
    out["score"] = out[votes].sum(axis=1)

    alignement_h = (out[votes] == 1).all(axis=1)
    alignement_b = (out[votes] == -1).all(axis=1)
    fenetre = r["fenetre_retournement"]
    score_min_prec = out["score"].shift(1).rolling(fenetre, min_periods=1).min()
    score_max_prec = out["score"].shift(1).rolling(fenetre, min_periods=1).max()

    ret_h = alignement_h & ~alignement_h.shift(1, fill_value=False) & (
        score_min_prec <= -r["score_retournement"]
    )
    ret_b = alignement_b & ~alignement_b.shift(1, fill_value=False) & (
        score_max_prec >= r["score_retournement"]
    )
    tendance = out["adx"] >= r["adx_tendance"]
    hausse = tendance & (out["score"] >= r["score_tendance"])
    baisse = tendance & (out["score"] <= -r["score_tendance"])

    seuil_compression = (
        out["bb_largeur"]
        .rolling(r["fenetre_compression"], min_periods=r["fenetre_compression"] // 2)
        .quantile(r["quantile_compression"])
    )
    stable = (out["adx"] < r["adx_range"]) & (out["bb_largeur"] <= seuil_compression)

    # L'ordre des conditions fixe la priorité : un retournement prime sur la tendance.
    out["etat"] = np.select(
        [ret_h, ret_b, hausse, baisse, stable],
        [RETOURNEMENT_HAUSSIER, RETOURNEMENT_BAISSIER, HAUSSE, BAISSE, STABILITE],
        default=NEUTRE,
    )
    # Pas d'état tant que les indicateurs n'ont pas assez d'historique.
    chauffe = out[["macd_signal", "bb_milieu", "momentum"]].isna().any(axis=1)
    out.loc[chauffe, "etat"] = NEUTRE

    prec = out["etat"].shift(1)
    entree_hausse = (out["etat"] == HAUSSE) & ~prec.isin([HAUSSE, RETOURNEMENT_HAUSSIER])
    entree_baisse = (out["etat"] == BAISSE) & ~prec.isin([BAISSE, RETOURNEMENT_BAISSIER])
    achat = (out["etat"] == RETOURNEMENT_HAUSSIER) | entree_hausse
    vente = (out["etat"] == RETOURNEMENT_BAISSIER) | entree_baisse
    if r.get("sortie_sur_sar", True):
        bascule_sar = (out["sar_tendance"] == -1) & (out["sar_tendance"].shift(1) == 1)
        vente |= bascule_sar & ~chauffe

    out["signal"] = np.select([achat, vente], [ACHAT, VENTE], default="")
    out["conviction"] = conviction(out)
    return out


def conviction(out: pd.DataFrame) -> pd.Series:
    """Indice de conviction de 0 à 100 : unanimité des votes pondérée par la force de tendance."""
    unanimite = out["score"].abs() / 4
    force = (out["adx"].clip(upper=50) / 50).fillna(0)
    return (100 * (0.6 * unanimite + 0.4 * force)).round(0)
