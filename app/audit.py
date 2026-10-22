"""Journal d'audit JSONL : qui a demandé quoi, avec quelles sources. Sans données personnelles."""
import hashlib
import hmac
import json
import threading
from datetime import UTC, datetime
from pathlib import Path

from app.security import redact


class AuditLog:
    def __init__(self, path: Path, secret: str):
        self.path = Path(path)
        self._secret = secret.encode()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def write(self, user: str, role: str, question: str, statut: str, sources: list[str],
              latence_ms: float, fournisseur: str) -> None:
        entry = {
            "ts": datetime.now(UTC).isoformat(timespec="milliseconds"),
            # Pseudonyme stable mais non réversible sans le secret (HMAC), contrairement à un simple hash.
            "utilisateur": hmac.new(self._secret, user.encode(), hashlib.sha256).hexdigest()[:16],
            "role": role,
            "question": redact(question)[:500],
            "statut": statut,
            "sources": sources,
            "latence_ms": latence_ms,
            "fournisseur": fournisseur,
        }
        with self._lock, self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
