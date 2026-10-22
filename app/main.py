"""API de l'assistant : authentification par clé, limitation de débit, métriques Prometheus, interface web."""
import hmac
import threading
import time
from collections import Counter, defaultdict, deque
from contextlib import asynccontextmanager
from functools import lru_cache
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import FileResponse, PlainTextResponse
from pydantic import BaseModel, Field

from app.config import groups_for, load_settings
from app.rag import Assistant

STATIC = Path(__file__).parent / "static"


@lru_cache
def get_assistant() -> Assistant:
    return Assistant(load_settings())


@asynccontextmanager
async def lifespan(_: FastAPI):
    get_assistant()                 # index construit au démarrage : la 1re requête n'attend pas, et une erreur
    yield                           # de configuration ou de document empêche le service de démarrer
    get_assistant().close()


app = FastAPI(title="Assistant IA d'entreprise", version="1.1.0", lifespan=lifespan,
              description="Répond aux questions des salariés à partir des documents internes, avec sources, "
                          "contrôle d'accès par rôle et masquage des données personnelles.")


class Question(BaseModel):
    question: str = Field(min_length=3, max_length=500, examples=["Combien de jours de télétravail par semaine ?"])


class Metrics:
    """Compteurs partagés entre les threads du serveur : protégés par un verrou."""

    def __init__(self):
        self._lock = threading.Lock()
        self.statuts, self.rejets = Counter(), Counter()
        self.latence_totale, self.requetes = 0.0, 0

    def observe(self, statut: str, latence_ms: float):
        with self._lock:
            self.statuts[statut] += 1
            self.requetes += 1
            self.latence_totale += latence_ms

    def reject(self, code: int):
        with self._lock:
            self.rejets[code] += 1

    def snapshot(self) -> tuple[dict, dict, float]:
        with self._lock:
            moyenne = self.latence_totale / self.requetes if self.requetes else 0.0
            return dict(self.statuts), dict(self.rejets), moyenne


METRICS = Metrics()
_FENETRES: dict[str, deque] = defaultdict(deque)
_FENETRES_LOCK = threading.Lock()


def _role_for_key(key: str, keys: dict) -> str | None:
    """Comparaison en temps constant : le temps de réponse ne révèle pas si une clé est « presque » bonne."""
    role = None
    for candidate, candidate_role in keys.items():
        if hmac.compare_digest(candidate.encode(), key.encode()):
            role = candidate_role
    return role


def get_role(x_api_key: str | None = Header(default=None)) -> tuple[str, str]:
    settings = get_assistant().settings
    role = _role_for_key(x_api_key, settings.api_keys) if x_api_key else None
    if role is None:
        METRICS.reject(401)
        raise HTTPException(401, "Clé d'API absente ou invalide (en-tête X-API-Key)")
    limite, maintenant = settings.rate_limit_per_minute, time.monotonic()
    with _FENETRES_LOCK:
        fenetre = _FENETRES[x_api_key]
        while fenetre and maintenant - fenetre[0] > 60:
            fenetre.popleft()
        depasse = len(fenetre) >= limite
        if not depasse:
            fenetre.append(maintenant)
    if depasse:
        METRICS.reject(429)
        raise HTTPException(429, f"Trop de requêtes : {limite} par minute maximum")
    return x_api_key, role


@app.get("/", include_in_schema=False)
def interface():
    return FileResponse(STATIC / "index.html")


@app.get("/health")
def health():
    return {"status": "ok", "documents": get_assistant().retriever.document_count}


@app.post("/ask")
def ask(body: Question, auth: tuple = Depends(get_role)):
    key, role = auth
    a = get_assistant().ask(body.question, role, user=key)
    METRICS.observe(a.statut, a.latence_ms)
    return {"reponse": a.reponse, "statut": a.statut, "sources": a.sources,
            "role": role, "latence_ms": a.latence_ms, "fournisseur": a.fournisseur}


@app.get("/documents")
def documents(auth: tuple = Depends(get_role)):
    """Liste uniquement les documents que ce rôle a le droit de consulter."""
    return get_assistant().retriever.visible_documents(groups_for(auth[1]))


@app.get("/metrics", response_class=PlainTextResponse)
def metrics():
    statuts, rejets, moyenne = METRICS.snapshot()
    lignes = ["# HELP assistant_requetes_total Questions traitées, par statut",
              "# TYPE assistant_requetes_total counter"]
    lignes += [f'assistant_requetes_total{{statut="{s}"}} {statuts.get(s, 0)}' for s in ("ok", "refus", "bloque")]
    lignes += ["# HELP assistant_rejets_total Requêtes rejetées avant traitement, par code HTTP",
               "# TYPE assistant_rejets_total counter"]
    lignes += [f'assistant_rejets_total{{code="{c}"}} {rejets.get(c, 0)}' for c in (401, 429)]
    lignes += ["# HELP assistant_latence_moyenne_ms Latence moyenne de réponse",
               "# TYPE assistant_latence_moyenne_ms gauge", f"assistant_latence_moyenne_ms {moyenne:.3f}"]
    return "\n".join(lignes) + "\n"
