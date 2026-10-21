"""Coûts de transaction réels : courtage par tranche, frais de change et TTF.

Le barème (paliers, change, TTF) est lu dans la section [frais] de config.toml.
"""

from dataclasses import dataclass


@dataclass
class Bareme:
    paliers: list[tuple[float, float]]  # (montant maximal inclus, frais fixe en €)
    au_dela_pct: float  # au-delà du dernier palier, % de la totalité de l'ordre
    change_pct: float = 0.0  # commission de change par opération, en %

    def courtage(self, montant: float) -> float:
        for plafond, fixe in self.paliers:
            if montant <= plafond:
                return fixe
        return montant * self.au_dela_pct / 100


def place(ticker: str) -> str:
    """Place de cotation déduite du ticker Yahoo : Euronext ou New York."""
    if ticker.startswith("^") or ticker.split(".")[-1] in ("PA", "AS", "BR", "LS"):
        return "euronext"  # un indice n'est pas négociable : on lui applique le barème de son marché
    return "us"


class ModeleFrais:
    def __init__(self, cfg_frais: dict, ticker: str, ttf: bool):
        b = cfg_frais[place(ticker)]
        self.bareme = Bareme([tuple(p) for p in b["paliers"]], b["au_dela_pct"], b.get("change_pct", 0.0))
        self.taux_ttf = cfg_frais["ttf_pct"] if ttf else 0.0

    def cout(self, montant: float, achat: bool) -> float:
        """Coût total en € d'un ordre de `montant` € (TTF à l'achat seulement)."""
        c = self.bareme.courtage(montant) + montant * self.bareme.change_pct / 100
        if achat:
            c += montant * self.taux_ttf / 100
        return c

    def taux(self, montant: float, achat: bool) -> float:
        """Coût rapporté au montant de l'ordre (0,00145 = 0,145 %)."""
        return self.cout(montant, achat) / montant if montant > 0 else 0.0
