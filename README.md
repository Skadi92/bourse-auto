# Bourse-auto

Outil d'alertes par mail sur actions et ETF. L'analyse est journalière et repose sur quatre indicateurs : MACD, bandes de Bollinger, SAR parabolique et momentum. L'ADX sert de filtre de régime de marché. L'outil tourne chaque soir de semaine sur GitHub Actions.

Les signaux sont techniques et automatiques. Ils ne constituent pas un conseil en investissement.

## Logique

Chaque indicateur vote +1 (haussier) ou -1 (baissier) :

| Indicateur | Haussier si |
|---|---|
| SAR parabolique | SAR sous le prix |
| MACD | ligne MACD au-dessus de sa ligne de signal |
| Momentum | variation positive sur 10 séances |
| Bollinger | clôture au-dessus de la bande médiane |

Le score va de -4 à +4. L'état du jour se déduit du score, par ordre de priorité :

1. **retournement haussier ou baissier** : les quatre votes s'alignent pour la première fois après une période où le score était orienté dans l'autre sens ;
2. **hausse ou baisse** : ADX d'au moins 25 (tendance installée) et score d'au moins 3 en valeur absolue ;
3. **stabilité** : ADX inférieur à 20 et bandes de Bollinger comprimées. C'est souvent le prélude à un mouvement fort, dont la direction reste inconnue ;
4. **neutre** : aucun des cas précédents.

Signaux :

- **ACHAT** : retournement haussier, ou entrée en hausse confirmée ;
- **VENTE** : retournement baissier, entrée en baisse confirmée, ou passage du SAR au-dessus du prix (stop suiveur, désactivable).

Un mail regroupe toutes les alertes d'une séance. Il n'est envoyé que s'il y a un signal, ou un changement d'état quand l'option `changements_etat` est activée. Le fichier `etat/etat.json`, mis à jour par le workflow, évite les doublons.

## Utilisation locale

```
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python -m bourse backtest              # rejoue les règles sur 10 ans
.venv\Scripts\python -m bourse backtest --periode 5y
.venv\Scripts\python -m bourse analyser --essai      # affiche le mail sans l'envoyer
.venv\Scripts\python -m pytest -q
```

Les instruments, les paramètres et les seuils se règlent dans `config.toml`. Les tickers suivent la nomenclature Yahoo Finance, avec le suffixe `.PA` pour Euronext Paris.

## Mise en place sur GitHub

1. Activez la validation en deux étapes sur le compte Gmail, puis créez un mot de passe d'application (Compte Google, Sécurité, Mots de passe des applications).
2. Créez un dépôt **privé** sur GitHub et poussez-y le projet.
3. Dans Settings, Secrets and variables, Actions, ajoutez les secrets suivants : `GMAIL_USER` (adresse Gmail), `GMAIL_APP_PASSWORD` (mot de passe d'application) et, si les alertes doivent partir vers une autre adresse, `MAIL_TO`.
4. Dans l'onglet Actions, lancez « Alertes bourse » à la main avec la commande `test-mail`. Elle envoie un mail au format réel avec l'état actuel de chaque instrument, sans modifier l'état mémorisé, ce qui valide les secrets Gmail même sans signal du jour.
5. Lancez ensuite la commande `analyser` avec `essai` coché, puis sans.

Le workflow s'exécute du lundi au vendredi à 22 h 30 UTC. Une bougie de la séance en cours n'est jamais analysée.

## Limites connues

- yfinance n'est pas une API officielle : il peut cesser de fonctionner ou renvoyer des données incomplètes. Le fichier `bourse/data.py` est le seul à modifier pour changer de source.
- GitHub peut retarder les déclenchements planifiés. Il désactive aussi les workflows planifiés des dépôts sans activité pendant 60 jours (règle documentée pour les dépôts publics, à vérifier pour un dépôt privé). Les commits quotidiens de l'état devraient suffire à maintenir l'activité.
- Le backtest est long uniquement. Il exécute les ordres à l'ouverture du lendemain et compte des frais fixes. Il ne modélise ni le glissement de prix ni la fiscalité.
