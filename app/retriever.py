"""Recherche BM25 sur index inversé, avec contrôle d'accès appliqué AVANT le classement.

Optimisations :
- index inversé : seuls les passages qui contiennent au moins un mot de la question sont notés ;
- normalisation de longueur pré-calculée pour chaque passage ;
- top-k par tas (heapq) au lieu d'un tri complet ;
- ensemble des passages visibles mis en cache par combinaison de groupes.
"""
import heapq
import math
from collections import Counter, defaultdict
from functools import lru_cache

from app.ingest import Chunk
from app.text import tokenize


class BM25Retriever:
    def __init__(self, chunks: list[Chunk], k1: float = 1.5, b: float = 0.75):
        self.chunks = chunks
        self.k1 = k1
        # Le titre et la section (comptée deux fois) sont indexés avec le texte : ils portent souvent les mots-clés.
        docs = [tokenize(f"{c.titre} {c.section} {c.section} {c.texte}") for c in chunks]
        avgdl = sum(map(len, docs)) / max(len(docs), 1)
        self.norm = [k1 * (1 - b + b * len(d) / avgdl) for d in docs]
        self.postings: dict[str, list[tuple[int, int]]] = defaultdict(list)
        for i, d in enumerate(docs):
            for term, freq in Counter(d).items():
                self.postings[term].append((i, freq))
        n = len(docs)
        self.idf = {t: math.log(1 + (n - len(p) + 0.5) / (len(p) + 0.5)) for t, p in self.postings.items()}
        self.postings = dict(self.postings)
        self.document_count = len({c.doc_id for c in chunks})
        self._visibles = lru_cache(maxsize=64)(self._compute_visibles)

    def _compute_visibles(self, groups: frozenset) -> frozenset:
        return frozenset(i for i, c in enumerate(self.chunks) if c.acces & groups)

    def search(self, question: str, groups: frozenset, k: int = 3,
               min_coverage: float = 0.0) -> list[tuple[Chunk, float]]:
        terms = list(dict.fromkeys(tokenize(question)))
        query = [t for t in terms if t in self.postings]
        n_terms = len(terms)
        if not query:
            return []
        visibles = self._visibles(groups)                       # contrôle d'accès d'abord
        scores: dict[int, float] = defaultdict(float)
        matched: dict[int, int] = defaultdict(int)
        k1p1 = self.k1 + 1
        for term in query:
            idf = self.idf[term]
            for i, freq in self.postings[term]:
                if i in visibles:
                    scores[i] += idf * freq * k1p1 / (freq + self.norm[i])
                    matched[i] += 1
        # À score égal, le passage le plus ancien dans le corpus passe devant : classement stable et reproductible.
        best = heapq.nlargest(k, scores.items(), key=lambda x: (x[1], -x[0]))
        return [(self.chunks[i], s) for i, s in best if matched[i] / n_terms >= min_coverage]

    def visible_documents(self, groups: frozenset) -> list[dict]:
        seen = {}
        for i in sorted(self._visibles(groups)):
            c = self.chunks[i]
            seen.setdefault(c.doc_id, {"id": c.doc_id, "titre": c.titre, "departement": c.departement})
        return list(seen.values())
