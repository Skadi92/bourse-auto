"""Point d'entrée : python -m bourse analyser | backtest."""

import argparse
import json
import sys
import tomllib
from pathlib import Path

from . import backtest, data, indicators, notifier, signals

RACINE = Path(__file__).resolve().parent.parent
FICHIER_ETAT = RACINE / "etat" / "etat.json"


def charger_config(chemin: Path) -> dict:
    with open(chemin, "rb") as f:
        return tomllib.load(f)


def analyser_ticker(ticker: str, periode: str, cfg: dict):
    df = data.charger(ticker, periode)
    df = indicators.calculer(df, cfg["indicateurs"])
    return signals.evaluer(df, cfg["regles"])


def lire_etat() -> dict:
    if FICHIER_ETAT.exists():
        return json.loads(FICHIER_ETAT.read_text(encoding="utf-8"))
    return {}


def ecrire_etat(etat: dict) -> None:
    FICHIER_ETAT.parent.mkdir(exist_ok=True)
    FICHIER_ETAT.write_text(json.dumps(etat, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def cmd_analyser(cfg: dict, essai: bool) -> int:
    etat = lire_etat()
    alertes, echecs = [], 0
    for inst in cfg["instruments"]:
        ticker, nom = inst["ticker"], inst.get("nom", inst["ticker"])
        try:
            df = analyser_ticker(ticker, cfg["donnees"]["periode_analyse"], cfg)
        except Exception as e:  # une source défaillante ne doit pas bloquer les autres tickers
            print(f"[ERREUR] {ticker} : {e}", file=sys.stderr)
            echecs += 1
            continue

        derniere = df.iloc[-1]
        date = df.index[-1].strftime("%Y-%m-%d")
        connu = etat.get(ticker, {})
        print(f"{ticker:10} {date}  {derniere['etat']:22} signal={derniere['signal'] or '-':6} "
              f"score={int(derniere['score']):+d} conviction={int(derniere['conviction'])}")

        if connu.get("date") == date:
            continue  # séance déjà traitée (relance du workflow)
        change = connu.get("etat") not in (None, derniere["etat"])
        if derniere["signal"] or (cfg["alertes"]["changements_etat"] and change):
            alertes.append({
                "ticker": ticker, "nom": nom, "date": date,
                "signal": derniere["signal"], "etat": derniere["etat"],
                "etat_precedent": connu.get("etat"), "donnees": derniere.to_dict(),
            })
        etat[ticker] = {"date": date, "etat": derniere["etat"], "signal": derniere["signal"]}

    if alertes:
        msg = notifier.construire(alertes, cfg["alertes"]["objet_prefixe"])
        if essai:
            print("\n--- Mail (mode essai, non envoyé) ---")
            print("Objet :", msg["Subject"])
            print(msg.get_body(("plain",)).get_content())
        else:
            notifier.envoyer(msg)
            print(f"Mail envoyé : {len(alertes)} alerte(s).")
    else:
        print("Aucune alerte.")

    if not essai:
        ecrire_etat(etat)
    return 1 if echecs == len(cfg["instruments"]) else 0


def cmd_backtest(cfg: dict, periode: str | None) -> int:
    periode = periode or cfg["donnees"]["periode_backtest"]
    pct = lambda x: f"{x * 100:7.1f} %"
    for inst in cfg["instruments"]:
        ticker = inst["ticker"]
        try:
            df = analyser_ticker(ticker, periode, cfg)
        except Exception as e:
            print(f"[ERREUR] {ticker} : {e}", file=sys.stderr)
            continue
        r, _ = backtest.executer(df, cfg["backtest"]["frais_bps"])
        print(f"\n{inst.get('nom', ticker)} ({ticker}), {r.debut:%d/%m/%Y} au {r.fin:%d/%m/%Y}")
        print(f"  {'':24}{'Stratégie':>10}{'Achat-cons.':>13}")
        print(f"  {'Performance totale':24}{pct(r.perf_strategie):>10}{pct(r.perf_achat_conservation):>13}")
        print(f"  {'Rendement annualisé':24}{pct(r.cagr_strategie):>10}{pct(r.cagr_achat_conservation):>13}")
        print(f"  {'Drawdown maximal':24}{pct(r.drawdown_max_strategie):>10}{pct(r.drawdown_max_achat_conservation):>13}")
        print(f"  Trades : {r.nb_trades}, taux de réussite : {pct(r.taux_reussite).strip()}, "
              f"exposition : {pct(r.exposition).strip()}")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(prog="bourse", description="Alertes techniques sur actions et ETF.")
    p.add_argument("--config", type=Path, default=RACINE / "config.toml")
    sp = p.add_subparsers(dest="commande", required=True)
    a = sp.add_parser("analyser", help="analyse la dernière séance et envoie les alertes")
    a.add_argument("--essai", action="store_true", help="affiche le mail sans l'envoyer ni modifier l'état")
    b = sp.add_parser("backtest", help="rejoue les règles sur l'historique")
    b.add_argument("--periode", help="ex. 5y, 10y, max")
    args = p.parse_args()

    cfg = charger_config(args.config)
    if args.commande == "analyser":
        return cmd_analyser(cfg, args.essai)
    return cmd_backtest(cfg, args.periode)


if __name__ == "__main__":
    sys.exit(main())
