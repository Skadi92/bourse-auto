"""Moteur de règles : régime de marché, état et signaux ACHAT / VENTE.

Chaque indicateur vote dans un sens (+1 haussier, -1 baissier) :
- SAR parabolique : prix au-dessus ou en dessous du SAR ;
- MACD : ligne MACD au-dessus ou en dessous de sa ligne de signal ;
- momentum : variation positive ou négative sur la période ;
- Bollinger : clôture au-dessus ou en dessous de la bande médiane.
Le score directionnel est la somme des votes (de -4 à +4). L'ADX et la largeur des
bandes de Bollinger qualifient l'état court terme (tendance ou marché stable), affiché
à titre descriptif. Les signaux ACHAT / VENTE viennent du régime de fond (fonction regime).
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

    out["conviction"] = conviction(out)
    return out


def regime(df: pd.DataFrame, rf: dict) -> pd.DataFrame:
    """Régime de fond et signaux ACHAT / VENTE, réservés aux mouvements d'ampleur.

    Indicateurs lents (moyenne mobile longue, momentum trois mois, MACD et SAR lents) et
    hystérésis : il faut une confirmation sur plusieurs séances pour changer de régime,
    et la zone entre les seuils d'entrée et de sortie ne déclenche rien.

    - ACHAT : cours au-dessus de la moyenne longue, momentum lent supérieur au seuil,
      MACD lent positif et SAR lent haussier, pendant `confirmation_jours` séances ;
    - VENTE (tendance) : cours sous la moyenne longue diminuée de la marge, momentum lent
      négatif et MACD lent négatif, pendant `confirmation_jours` séances ;
    - VENTE (krach) : repli depuis le plus haut récent supérieur à `krach_k` fois la
      volatilité de la période, sans attendre de confirmation.
    """
    out = df.copy()
    c = out["Close"]
    cond_achat = (
        (c > out["f_mm"])
        & (out["f_momentum"] > rf["momentum_achat_min"])
        & (out["f_macd_hist"] > 0)
        & (out["f_sar_tendance"] == 1)
    ).to_numpy()
    cond_vente = (
        (c < out["f_mm"] * (1 - rf["marge_vente"] / 100))
        & (out["f_momentum"] < 0)
        & (out["f_macd_hist"] < 0)
    ).to_numpy()
    krach = (out["f_repli"] <= -rf["krach_k"] * out["f_volatilite"]).to_numpy()
    pret = out["f_mm"].notna().to_numpy()

    n, conf, delai = len(out), rf["confirmation_jours"], rf["delai_apres_vente"]
    etats = np.full(n, NEUTRE, dtype=object)
    signaux = np.full(n, "", dtype=object)
    motifs = np.full(n, "", dtype=object)
    courant, serie_achat, serie_vente, derniere_vente = NEUTRE, 0, 0, -10**9

    for t in range(n):
        if not pret[t]:
            continue
        serie_achat = serie_achat + 1 if cond_achat[t] else 0
        serie_vente = serie_vente + 1 if cond_vente[t] else 0
        if courant != BAISSE and krach[t]:
            courant, signaux[t], motifs[t] = BAISSE, VENTE, "krach"
            derniere_vente, serie_achat = t, 0
        elif courant != BAISSE and serie_vente >= conf:
            courant, signaux[t], motifs[t] = BAISSE, VENTE, "tendance"
            derniere_vente, serie_achat = t, 0
        elif courant != HAUSSE and serie_achat >= conf and t - derniere_vente >= delai:
            courant, signaux[t], motifs[t] = HAUSSE, ACHAT, "tendance"
        etats[t] = courant

    out["regime"], out["signal"], out["motif"] = etats, signaux, motifs
    out["force"] = force(out)
    return out


def force(out: pd.DataFrame) -> pd.Series:
    """Force du mouvement de 0 à 100, pour classer les signaux entre instruments.

    Momentum lent et écart à la moyenne longue sont exprimés en multiples de la volatilité
    de l'instrument, pour comparer un ETF peu volatil et une action nerveuse.
    """
    vol = out["f_volatilite"].replace(0, np.nan)
    z_momentum = (out["f_momentum"] / vol).abs()
    z_ecart = ((out["Close"] / out["f_mm"] - 1) * 100 / vol).abs()
    ampleur = ((z_momentum + z_ecart) / 2 / 2).clip(upper=1)
    tendance = (out["adx"].clip(upper=50) / 50).fillna(0)
    return (100 * (0.7 * ampleur + 0.3 * tendance)).fillna(0).round(0)


def conviction(out: pd.DataFrame) -> pd.Series:
    """Indice de conviction de 0 à 100 : unanimité des votes pondérée par la force de tendance."""
    unanimite = out["score"].abs() / 4
    force = (out["adx"].clip(upper=50) / 50).fillna(0)
    return (100 * (0.6 * unanimite + 0.4 * force)).round(0)
