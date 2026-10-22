"""Configuration par variables d'environnement (lue au démarrage, jamais codée en dur)."""
import json
import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Clés de démonstration uniquement. En production : variable API_KEYS (JSON) issue d'un coffre de secrets.
DEMO_API_KEYS = {
    "demo-employe": "employe",
    "demo-support": "support",
    "demo-it": "it",
    "demo-rh": "rh",
    "demo-direction": "direction",
}

# Chaque rôle hérite de groupes d'accès : un administrateur IT est aussi un salarié.
ROLE_GROUPS = {
    "employe": {"employe"},
    "support": {"employe", "support"},
    "it": {"employe", "it"},
    "rh": {"employe", "rh"},
    "finance": {"employe", "finance"},
    "achats": {"employe", "achats"},
    "direction": {"employe", "direction"},
}


PROVIDERS = ("extractif", "ollama", "openai")
DEMO_AUDIT_SECRET = "secret-de-demonstration"  # noqa: S105  (démo : refusé dès que de vraies clés existent)


def _api_keys(raw: str | None) -> dict:
    if not raw:
        return DEMO_API_KEYS
    try:
        keys = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(f"API_KEYS n'est pas un JSON valide : {e}") from None
    if not isinstance(keys, dict) or not keys:
        raise ValueError('API_KEYS doit être un objet JSON non vide, par exemple {"cle": "employe"}')
    return keys


def groups_for(role: str) -> frozenset:
    return frozenset(ROLE_GROUPS.get(role, {role}))


@dataclass(frozen=True)
class Settings:
    docs_dir: Path
    audit_log: Path
    top_k: int
    min_score: float
    min_coverage: float
    llm_provider: str          # extractif | ollama | openai
    ollama_url: str
    ollama_model: str
    openai_base_url: str
    openai_api_key: str
    openai_model: str
    llm_timeout: float
    rate_limit_per_minute: int
    api_keys: dict
    audit_secret: str
    max_question_chars: int

    def __post_init__(self):
        """Arrête le démarrage sur une configuration incohérente, plutôt que d'échouer en pleine requête."""
        if self.llm_provider not in PROVIDERS:
            raise ValueError(f"LLM_PROVIDER doit valoir {', '.join(PROVIDERS)} (reçu : {self.llm_provider})")
        if self.top_k < 1 or self.rate_limit_per_minute < 1 or self.max_question_chars < 10:
            raise ValueError("TOP_K, RATE_LIMIT_PER_MINUTE et MAX_QUESTION_CHARS doivent être positifs")
        if not 0 <= self.min_coverage <= 1:
            raise ValueError("MIN_COVERAGE doit être compris entre 0 et 1")
        inconnus = set(self.api_keys.values()) - set(ROLE_GROUPS)
        if inconnus:
            raise ValueError(f"API_KEYS contient des rôles inconnus : {sorted(inconnus)}")
        if self.llm_provider == "openai" and not self.openai_api_key:
            raise ValueError("LLM_PROVIDER=openai nécessite OPENAI_API_KEY")
        if self.api_keys != DEMO_API_KEYS and self.audit_secret == DEMO_AUDIT_SECRET:
            # De vraies clés avec le secret public de démonstration : la pseudonymisation ne protégerait rien.
            raise ValueError("AUDIT_SECRET doit être défini dès que API_KEYS contient de vraies clés")


def load_settings() -> Settings:
    env = os.getenv
    return Settings(
        docs_dir=Path(env("DOCS_DIR", ROOT / "data" / "docs")),
        audit_log=Path(env("AUDIT_LOG", ROOT / "logs" / "audit.jsonl")),
        top_k=int(env("TOP_K", "3")),
        min_score=float(env("MIN_SCORE", "2.0")),
        min_coverage=float(env("MIN_COVERAGE", "0.5")),
        llm_provider=env("LLM_PROVIDER", "extractif"),
        ollama_url=env("OLLAMA_URL", "http://localhost:11434"),
        ollama_model=env("OLLAMA_MODEL", "qwen2.5:3b"),
        openai_base_url=env("OPENAI_BASE_URL", "https://api.openai.com/v1"),
        openai_api_key=env("OPENAI_API_KEY", ""),
        openai_model=env("OPENAI_MODEL", "gpt-4o-mini"),
        llm_timeout=float(env("LLM_TIMEOUT", "30")),
        rate_limit_per_minute=int(env("RATE_LIMIT_PER_MINUTE", "30")),
        api_keys=_api_keys(env("API_KEYS")),
        # Secret de pseudonymisation du journal d'audit : à fournir en production (coffre de secrets).
        audit_secret=env("AUDIT_SECRET", DEMO_AUDIT_SECRET),
        max_question_chars=int(env("MAX_QUESTION_CHARS", "500")),
    )
