#!/usr/bin/env python3
"""suivi-decomp : récupère les rapports objdiff que chaque projet publie dans sa CI
GitHub, garde leur historique dans data/ et génère le site statique dans site/.

Dépendances : Python 3 et `gh` connecté (ou GH_TOKEN). `--offline` régénère le
site sans rien télécharger."""
import html
import io
import json
import os
import shutil
import subprocess
import sys
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
SITE = ROOT / "site"
# ponytail: quelques rapports par projet et par passage ; l'historique se remplit
# au fil des passages, dans la limite des 90 jours de rétention des artefacts.
MAX_NEW = int(os.environ.get("MAX_NEW", "3"))
MEASURES = ("matched_code_percent", "complete_code_percent", "matched_data_percent",
            "complete_data_percent", "total_code", "matched_code", "total_data",
            "total_functions", "matched_functions", "total_units", "complete_units")


def gh(path, raw=False):
    r = subprocess.run(["gh", "api", path], capture_output=True)
    if r.returncode:
        raise RuntimeError(f"gh api {path} : {r.stderr.decode().strip()}")
    return r.stdout if raw else json.loads(r.stdout)


def measures(m):
    # JSON protobuf : les zéros sont omis et les u64 arrivent en chaînes.
    return {k: round(float(m.get(k, 0)), 4) for k in MEASURES}


def data_file(p):
    return DATA / (p["repo"].replace("/", "__") + ".json")


def load(p):
    f = data_file(p)
    return json.loads(f.read_text()) if f.exists() else {"history": []}


def pick_artifact(names):
    reports = sorted(n for n in names if "report" in n.lower())
    # Plusieurs versions du jeu : la version américaine d'abord, sinon la première.
    return next((n for n in reports if "E0" in n), reports[0] if reports else None)


def read_report(repo, artifact_id):
    z = zipfile.ZipFile(io.BytesIO(gh(f"repos/{repo}/actions/artifacts/{artifact_id}/zip", raw=True)))
    names = [n for n in z.namelist() if n.endswith(".json")]
    name = "report.json" if "report.json" in names else names[0]
    return json.loads(z.read(name))


def find_report(repo, run_id, name):
    # Liste par run : la liste globale des artefacts casse sur les gros dépôts.
    arts = gh(f"repos/{repo}/actions/runs/{run_id}/artifacts?per_page=100")["artifacts"]
    name = name or pick_artifact({a["name"] for a in arts})
    return next((a for a in arts if a["name"] == name), None)


def add_snapshot(d, run, r):
    commit = run.get("head_commit") or {}
    snap = {"sha": run["head_sha"],
            "time": commit.get("timestamp") or run["created_at"],
            "message": (commit.get("message") or "").split("\n")[0],
            "measures": measures(r.get("measures", {})),
            "categories": {c["id"]: measures(c.get("measures", {})) for c in r.get("categories", [])}}
    d["category_names"] = {c["id"]: c.get("name", c["id"]) for c in r.get("categories", [])} or d.get("category_names", {})
    d["history"].append(snap)
    if snap["time"] >= d.get("units_time", ""):
        d["units_time"] = snap["time"]
        d["units"] = [[u.get("name", "?"), int(float(u["measures"].get("total_code", 0))),
                       round(float(u["measures"].get("fuzzy_match_percent", 0)), 2),
                       int(bool(u.get("metadata", {}).get("complete"))),
                       u.get("metadata", {}).get("progress_categories", [])]
                      for u in r.get("units", []) if float(u.get("measures", {}).get("total_code", 0)) > 0]


def update(p):
    repo = p["repo"]
    try:
        d = load(p)
        d.setdefault("branch", gh(f"repos/{repo}")["default_branch"])
        d.setdefault("artifact", p.get("artifact"))
        source = f"workflows/{d['workflow']}/runs" if d.get("workflow") else "runs"
        runs = gh(f"repos/{repo}/actions/{source}?branch={d['branch']}&event=push&status=success&per_page=100")["workflow_runs"]
        seen = {h["sha"] for h in d["history"]}
        new = 0
        for run in [r for r in runs if r["head_sha"] not in seen][:MAX_NEW * 3]:
            if new == MAX_NEW:
                break
            a = find_report(repo, run["id"], d["artifact"])
            if not a or run["head_sha"] in seen:
                continue
            if a["expired"]:
                break  # les runs plus anciens ont expiré aussi
            d["artifact"], d["workflow"] = a["name"], run["workflow_id"]
            add_snapshot(d, run, read_report(repo, a["id"]))
            seen.add(run["head_sha"])
            new += 1
        if not d["history"]:
            return f"{repo} : aucun rapport objdiff dans la CI publique"
        d["history"].sort(key=lambda h: h["time"])
        # indent=0 : une valeur par ligne, git stocke les différences en petit.
        data_file(p).write_text(json.dumps(d, indent=0, ensure_ascii=False))
        return f"{repo} : {new} nouveau(x) rapport(s)"
    except (RuntimeError, KeyError, IndexError, ValueError, zipfile.BadZipFile) as e:
        return f"{repo} : ÉCHEC {e}"


E = html.escape
FOOTER = """<footer>
<p>Réimplémentation indépendante, écrite de zéro : aucun code de decomp.dev n'est utilisé,
et ce site n'a aucun lien avec decomp.dev ni avec son auteur.</p>
<p>Les chiffres sont les rapports objdiff que chaque projet publie lui-même dans sa CI publique.
Une décompilation est d'abord un travail de recherche, pas un portage. Un projet est retiré
sur simple demande de ses mainteneurs.
<a href="https://github.com/adrbn/suivi-decomp">Code</a></p>
</footer>"""


def page(title, crumbs, body, depth):
    up = "../" * depth or "./"
    return f"""<!doctype html>
<html lang="fr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{E(title)}</title><link rel="stylesheet" href="{up}style.css"></head>
<body><header><a class="brand" href="{up}">suivi-decomp</a>{crumbs}</header>
<main>{body}</main>{FOOTER}<script src="{up}app.js"></script></body></html>
"""


def pct(v):
    return f"{v:.2f}".replace(".", ",") + " %"


def badge(left, right):
    wl, wr = 6.5 * len(left) + 12, 6.5 * len(right) + 12
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{wl + wr:.0f}" height="20" role="img" '
            f'aria-label="{E(left)} : {E(right)}"><rect width="{wl:.0f}" height="20" fill="#555"/>'
            f'<rect x="{wl:.0f}" width="{wr:.0f}" height="20" fill="#2f9e5f"/>'
            f'<g fill="#fff" font-family="Verdana,sans-serif" font-size="11" text-anchor="middle">'
            f'<text x="{wl / 2:.0f}" y="14">{E(left)}</text><text x="{wl + wr / 2:.0f}" y="14">{E(right)}</text></g></svg>')


def summary(m):
    s = f"{pct(m['matched_code_percent'])} décompilé"
    return s + (f" | {pct(m['complete_code_percent'])} entièrement lié" if m["complete_code_percent"] else "")


def render(projects):
    if SITE.exists():
        shutil.rmtree(SITE)
    shutil.copytree(ROOT / "static", SITE)
    cards, platforms = [], sorted({p["platform"] for p in projects})
    for p in projects:
        d = load(p)
        if not d["history"]:
            continue
        repo, last = p["repo"], d["history"][-1]
        m, short = last["measures"], last["sha"][:7]
        commit = f'<a href="https://github.com/{E(repo)}/commit/{E(last["sha"])}"><code>{short}</code></a>'
        cards.append(
            f'<li class="card" data-name="{E(p["name"])}" data-time="{E(last["time"])}" '
            f'data-pct="{m["matched_code_percent"]}" data-matched="{m["matched_code"]}" '
            f'data-total="{m["total_code"]}" data-plat="{E(p["platform"])}">'
            f'<a class="title" href="{E(repo)}/"><h2>{E(p["name"])}</h2></a><span class="plat">{E(p["platform"])}</span>'
            f'<div class="bar code" data-m="{m["matched_code_percent"]}" data-c="{m["complete_code_percent"]}"></div>'
            f'<p>{summary(m)}</p><p class="muted">Mis à jour <time datetime="{E(last["time"])}"></time> '
            f'dans le commit {commit}</p></li>')
        payload = json.dumps({"repo": repo, "history": d["history"], "units": d.get("units", []),
                              "categories": d.get("category_names", {})}, ensure_ascii=False)
        body = (f'<h1>{E(p["name"])} est décompilé à {pct(m["matched_code_percent"])}</h1>'
                + (f'<p class="sub">{pct(m["complete_code_percent"])} entièrement lié</p>' if m["complete_code_percent"] else "")
                + f'<p class="muted">{E(p["platform"])} · <a href="https://github.com/{E(repo)}">{E(repo)}</a> · '
                f'dernier rapport : commit {commit} {E(last["message"])}</p>'
                '<label class="pick">Catégorie <select id="cat"><option value="">Tout</option></select></label>'
                '<section id="bars"></section><h2>Historique</h2><div id="chart"></div>'
                '<h2>Unités</h2><input id="filter" type="search" placeholder="Filtre, ex. : camera &lt;70% &gt;10ko">'
                '<div id="treemap"></div><p class="muted legend">Surface = taille du code · couleur = part décompilée '
                '(rouge 0 %, vert 100 %, vert foncé = entièrement lié)</p>'
                '<h2>Rapports</h2><table id="commits"></table>'
                f'<p class="muted">Badge : <code>![décompilé](https://adrbn.github.io/suivi-decomp/{E(repo)}/badge.svg)</code></p>'
                f'<script type="application/json" id="data">{payload.replace("<", chr(92) + "u003c")}</script>')
        crumbs = f' / <span>{E(p["name"])}</span>'
        out = SITE / repo
        out.mkdir(parents=True, exist_ok=True)
        (out / "index.html").write_text(page(f"{p['name']} · suivi-decomp", crumbs, body, 2))
        (out / "badge.svg").write_text(badge("décompilé", pct(m["matched_code_percent"])))
    options = "".join(f'<option>{E(x)}</option>' for x in platforms)
    body = ('<div class="tools"><label>Trier <select id="sort"><option value="updated">Dernière mise à jour</option>'
            '<option value="name">Nom</option><option value="pct">Part décompilée</option>'
            '<option value="matched">Code décompilé</option><option value="total">Taille du code</option></select></label>'
            f'<label>Plateforme <select id="plat"><option value="">Toutes</option>{options}</select></label></div>'
            f'<ul id="projects">{"".join(cards)}</ul>')
    (SITE / "index.html").write_text(page("Projets · suivi-decomp", "", body, 0))
    return len(cards)


def main():
    projects = json.loads((ROOT / "projects.json").read_text())
    DATA.mkdir(exist_ok=True)
    if "--offline" not in sys.argv:
        with ThreadPoolExecutor(8) as ex:
            for line in ex.map(update, projects):
                print(line, flush=True)
    print(f"site/ : {render(projects)} projets publiés")


if __name__ == "__main__":
    main()
