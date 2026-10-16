# suivi-decomp

Suivi de la progression des projets de décompilation « matching » : part du code
décompilée et entièrement liée, historique par commit, carte des unités, badge.

**Site : https://adrbn.github.io/suivi-decomp/**

## D'où viennent les chiffres

Chaque projet publie déjà un rapport [objdiff](https://github.com/encounter/objdiff)
(`report.json`) dans les artefacts de sa CI GitHub publique. `build.py` lit les
rapports des commits poussés sur la branche principale, garde leur historique dans
`data/` et génère un site statique. Une action GitHub le refait toutes les 6 heures.

```bash
python3 build.py            # récupère les nouveaux rapports puis génère site/
python3 build.py --offline  # régénère site/ depuis data/ sans rien télécharger
```

Il faut Python 3 et `gh` connecté (ou `GH_TOKEN`). Les artefacts expirent après
90 jours au plus : l'historique commence là.

## Ce que ce projet respecte

decomp.dev a fermé son index public en octobre 2026. Son auteur se réserve tous
les droits sur son code. Donc :

- **Aucun code de decomp.dev n'est utilisé.** Tout est écrit de zéro ; seul le
  format public de rapport d'objdiff (sous licence MIT/Apache) est lu.
- **Aucun lien** avec decomp.dev ni avec son auteur, aucun nom ni logo repris.
- **Retrait sur demande** : un mainteneur qui ne veut pas voir son projet ici
  ouvre une issue ou retire la ligne de `projects.json`, c'est fait.
- **Une décompilation n'est pas un portage.** Ce site suit un travail de
  recherche ; il ne dit rien sur la jouabilité d'un portage.

## Ajouter un projet

Une ligne dans `projects.json` : `repo`, `name`, `platform`, et `artifact` si
l'artefact du rapport n'est pas deviné (par défaut : le premier `*_report`,
la version `E0…` en priorité).
