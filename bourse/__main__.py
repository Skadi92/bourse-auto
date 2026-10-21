"""Point d'entrée : python -m bourse analyser | backtest | test-mail."""

import argparse
import json
import sys
import time
import tomllib
from pathlib import Path

from . import backtest, charts, data, indicators, notifier, signals

RACINE = Path(__file__).resolve().parent.parent
FICHIER_ETAT = RACINE / "etat" / "etat.json"


def charger_config(chemin: Path) -> dict:
    with open(chemin, "rb") as f:
        return tomllib.load(f)


def analyser_ticker(ticker: str, periode: str, cfg: dict):
    for essai in range(2):  # une relance en cas de refus ponctuel de Yahoo
        try:
            df = data.charger(ticker, periode)
            break
        except Exception:
            if essai:
                raise
            time.sleep(3)
    df = indicators.calculer(df, cfg["indicateurs"], cfg["fond"])
    return signals.regime(signals.evaluer(df, cfg["regles"]), cfg["regles_fond"])


def tracer(df, ticker: str) -> bytes | None:
    """Graphique de tendance ; un échec de rendu ne doit pas empêcher l'alerte."""
    try:
        return charts.graphique(df)
    except Exception as e:
        print(f"[AVERTISSEMENT] graphique {ticker} non généré : {e}", file=sys.stderr)
        return None


def lire_etat() -> dict:
    if FICHIER_ETAT.exists():
        return json.loads(FICHIER_ETAT.read_text(encoding="utf-8"))
    return {}


def ecrire_etat(etat: dict) -> None:
    FICHIER_ETAT.parent.mkdir(exist_ok=True)
    FICHIER_ETAT.write_text(json.dumps(etat, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def analyser_tous(cfg: dict) -> tuple[list[dict], int]:
    """Analyse chaque instrument ; renvoie les résultats (sans graphique) et le nombre d'échecs."""
    resultats, echecs = [], 0
    for inst in cfg["instruments"]:
        ticker = inst["ticker"]
        try:
            df = analyser_ticker(ticker, cfg["donnees"]["periode_analyse"], cfg)
        except Exception as e:  # une source défaillante ne doit pas bloquer les autres tickers
            print(f"[ERREUR] {ticker} : {e}", file=sys.stderr)
            echecs += 1
            continue
        d = df.iloc[-1]
        resultats.append({
            "ticker": ticker, "nom": inst.get("nom", ticker), "toujours": inst.get("toujours", False),
            "date": df.index[-1].strftime("%Y-%m-%d"),
            "signal": d["signal"], "motif": d["motif"], "regime": d["regime"],
            "etat": d["etat"], "force": float(d["force"]), "donnees": d.to_dict(), "df": df,
        })
        print(f"{ticker:10} {resultats[-1]['date']}  régime={d['regime']:7} "
              f"signal={d['signal'] or '-':6} force={int(d['force']):3}  court terme={d['etat']}")
    return resultats, echecs


def selectionner(resultats: list[dict], n: int) -> tuple[list[dict], list[dict]]:
    """Les n résultats de plus forte force (avec graphique) et les autres."""
    tries = sorted(resultats, key=lambda a: a["force"], reverse=True)
    retenus, autres = tries[:n], tries[n:]
    for a in retenus:
        a["graphique"] = tracer(a["df"], a["ticker"])
    return retenus, autres


def suivis_permanents(resultats: list[dict], deja: list[dict]) -> list[dict]:
    """Instruments marqués « toujours » et absents des signaux détaillés, avec graphique."""
    vus = {a["ticker"] for a in deja}
    suivis = [a for a in resultats if a["toujours"] and a["ticker"] not in vus]
    for a in suivis:
        a["graphique"] = tracer(a["df"], a["ticker"])
    return suivis


def cmd_analyser(cfg: dict, essai: bool) -> int:
    etat = lire_etat()
    resultats, echecs = analyser_tous(cfg)

    signaux = []
    for a in resultats:
        connu = etat.get(a["ticker"], {})
        a["regime_precedent"] = connu.get("regime")
        nouveau = connu.get("date") != a["date"]  # séance pas encore traitée
        # Les ventes passent toujours (protection) ; seuls les achats sont filtrés par la force.
        assez_fort = a["signal"] == signals.VENTE or a["force"] >= cfg["alertes"]["force_min_achat"]
        if nouveau and a["signal"] and assez_fort:
            signaux.append(a)
        etat[a["ticker"]] = {"date": a["date"], "regime": a["regime"], "signal": a["signal"]}

    if signaux:
        retenus, autres = selectionner(signaux, cfg["alertes"]["max_par_mail"])
        msg = notifier.construire(retenus, cfg["alertes"]["objet_prefixe"], autres=autres,
                                  suivis=suivis_permanents(resultats, retenus))
        if essai:
            print("\n--- Mail (mode essai, non envoyé) ---")
            print("Objet :", msg["Subject"])
            print(msg.get_body(("plain",)).get_content())
        else:
            notifier.envoyer(msg)
            print(f"Mail envoyé : {len(retenus)} signal(aux) détaillé(s) sur {len(signaux)}.")
    else:
        print("Aucun signal.")

    if not essai:
        ecrire_etat(etat)
    return 1 if echecs == len(cfg["instruments"]) else 0


def cmd_test_mail(cfg: dict) -> int:
    """Envoie un mail au format réel avec les instruments de plus forte force, sans toucher à l'état."""
    etat = lire_etat()
    resultats, _ = analyser_tous(cfg)
    if not resultats:
        print("Aucune donnée disponible, mail non envoyé.", file=sys.stderr)
        return 1
    for a in resultats:
        a["regime_precedent"] = etat.get(a["ticker"], {}).get("regime")
    retenus, _ = selectionner([a for a in resultats if not a["toujours"]],
                              cfg["alertes"]["max_par_mail"])
    msg = notifier.construire(retenus, cfg["alertes"]["objet_prefixe"],
                              "Test d'envoi, mouvements les plus forts",
                              suivis=suivis_permanents(resultats, retenus))
    notifier.envoyer(msg)
    print(f"Mail de test envoyé à {msg['To']} ({len(retenus)} instrument(s)).")
    return 0


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
        df = df[df["f_mm"].notna()]  # même point de départ pour la stratégie et l'achat-conservation
        if len(df) < 2:
            print(f"[ERREUR] {ticker} : historique trop court", file=sys.stderr)
            continue
        r, _ = backtest.executer(df, cfg["backtest"]["frais_bps"])
        annees = max((r.fin - r.debut).days / 365.25, 1 / 365.25)
        print(f"\n{inst.get('nom', ticker)} ({ticker}), {r.debut:%d/%m/%Y} au {r.fin:%d/%m/%Y}")
        print(f"  {'':24}{'Stratégie':>10}{'Achat-cons.':>13}")
        print(f"  {'Performance totale':24}{pct(r.perf_strategie):>10}{pct(r.perf_achat_conservation):>13}")
        print(f"  {'Rendement annualisé':24}{pct(r.cagr_strategie):>10}{pct(r.cagr_achat_conservation):>13}")
        print(f"  {'Drawdown maximal':24}{pct(r.drawdown_max_strategie):>10}{pct(r.drawdown_max_achat_conservation):>13}")
        print(f"  Trades : {r.nb_trades} ({r.nb_trades / annees:.1f} par an), "
              f"taux de réussite : {pct(r.taux_reussite).strip()}, exposition : {pct(r.exposition).strip()}")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(prog="bourse", description="Alertes techniques sur actions et ETF.")
    p.add_argument("--config", type=Path, default=RACINE / "config.toml")
    sp = p.add_subparsers(dest="commande", required=True)
    a = sp.add_parser("analyser", help="analyse la dernière séance et envoie les alertes")
    a.add_argument("--essai", action="store_true", help="affiche le mail sans l'envoyer ni modifier l'état")
    b = sp.add_parser("backtest", help="rejoue les règles sur l'historique")
    b.add_argument("--periode", help="ex. 5y, 10y, max")
    sp.add_parser("test-mail", help="envoie un mail de test avec les mouvements les plus forts")
    args = p.parse_args()

    cfg = charger_config(args.config)
    if args.commande == "analyser":
        return cmd_analyser(cfg, args.essai)
    if args.commande == "test-mail":
        return cmd_test_mail(cfg)
    return cmd_backtest(cfg, args.periode)


if __name__ == "__main__":
    sys.exit(main())
