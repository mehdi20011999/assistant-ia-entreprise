"""Banc de performance : latence (p50, p95, p99), débit et temps de démarrage.

Usage : python -m eval.bench [--multiplier 50]
--multiplier duplique le corpus pour simuler une base documentaire plus grande.
"""
import argparse
import json
import os
import shutil
import statistics
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("AUDIT_LOG", str(Path(tempfile.gettempdir()) / "bench-audit.jsonl"))

from app.config import load_settings  # noqa: E402
from app.rag import Assistant  # noqa: E402


def corpus_agrandi(multiplier: int) -> Path:
    """Copie chaque document `multiplier` fois sous un nouvel identifiant."""
    dest = Path(tempfile.mkdtemp(prefix="corpus-"))
    for src in (ROOT / "data" / "docs").glob("*.md"):
        texte = src.read_text(encoding="utf-8")
        doc_id = texte.split("id:", 1)[1].split("\n", 1)[0].strip()
        for n in range(multiplier):
            (dest / f"{src.stem}-{n}.md").write_text(texte.replace(f"id: {doc_id}", f"id: {doc_id}-{n}", 1),
                                                     encoding="utf-8")
    return dest


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--multiplier", type=int, default=1)
    p.add_argument("--repetitions", type=int, default=20)
    p.add_argument("--budget-p95", type=float, default=None,
                   help="échoue (code 1) si la latence p95 dépasse ce budget, en millisecondes")
    args = p.parse_args()

    docs = corpus_agrandi(args.multiplier) if args.multiplier > 1 else ROOT / "data" / "docs"
    os.environ["DOCS_DIR"] = str(docs)
    questions = json.loads((ROOT / "eval" / "questions.json").read_text(encoding="utf-8"))

    debut = time.perf_counter()
    assistant = Assistant(load_settings())
    demarrage = (time.perf_counter() - debut) * 1000

    latences = []
    debut = time.perf_counter()
    for _ in range(args.repetitions):
        for q in questions:
            t = time.perf_counter()
            assistant.ask(q["question"], q["role"], user="bench")
            latences.append((time.perf_counter() - t) * 1000)
    total = time.perf_counter() - debut
    latences.sort()
    pct = lambda p: latences[min(len(latences) - 1, int(p / 100 * len(latences)))]  # noqa: E731
    resultat = {
        "passages_indexes": len(assistant.retriever.chunks),
        "demarrage_ms": round(demarrage, 1),
        "requetes": len(latences),
        "latence_p50_ms": round(pct(50), 3),
        "latence_p95_ms": round(pct(95), 3),
        "latence_p99_ms": round(pct(99), 3),
        "latence_moyenne_ms": round(statistics.mean(latences), 3),
        "debit_req_par_s": round(len(latences) / total, 1),
    }
    print(json.dumps(resultat, indent=2))
    if args.multiplier > 1:
        shutil.rmtree(docs, ignore_errors=True)
    if args.budget_p95 is not None and resultat["latence_p95_ms"] > args.budget_p95:
        print(f"ÉCHEC : p95 = {resultat['latence_p95_ms']} ms > budget {args.budget_p95} ms")
        sys.exit(1)


if __name__ == "__main__":
    main()
