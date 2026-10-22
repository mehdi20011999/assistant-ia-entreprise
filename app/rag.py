"""Pipeline : garde-fou -> recherche filtrée par rôle -> génération -> vérification -> audit.

Les données personnelles sont masquées UNE FOIS, au chargement des documents : elles ne sont jamais
indexées, jamais envoyées au modèle et jamais renvoyées (protection des données dès la conception).
"""
import re
import time
from dataclasses import dataclass, field, replace

from app.audit import AuditLog
from app.config import Settings, groups_for
from app.ingest import load_chunks
from app.llm import ExtractiveLLM, get_llm
from app.retriever import BM25Retriever
from app.security import detect_injection, redact

REFUS = "Je ne trouve pas cette information dans les documents auxquels vous avez accès."
BLOQUE = ("Je ne peux pas traiter cette demande : elle ressemble à une tentative de contourner "
          "mes règles de sécurité. Reformulez votre question sur les procédures de l'entreprise.")
_CITATION = re.compile(r"\[(\d+)\]")
_REFUS_MODELE = re.compile(r"je ne trouve pas|pas dans les documents|aucune information", re.IGNORECASE)


@dataclass(slots=True)
class Answer:
    reponse: str
    statut: str                       # ok | refus | bloque
    sources: list = field(default_factory=list)
    latence_ms: float = 0.0
    fournisseur: str = ""


class Assistant:
    def __init__(self, settings: Settings):
        self.settings = settings
        chunks = [replace(c, texte=redact(c.texte)) for c in load_chunks(settings.docs_dir)]
        self.retriever = BM25Retriever(chunks)
        self.llm = get_llm(settings)
        self.fallback = ExtractiveLLM()
        self.audit = AuditLog(settings.audit_log, settings.audit_secret)

    def close(self) -> None:
        if hasattr(self.llm, "close"):
            self.llm.close()

    def ask(self, question: str, role: str, user: str = "anonyme") -> Answer:
        debut = time.perf_counter()
        question = question.strip()[: self.settings.max_question_chars]
        answer = self._answer(question, role)
        answer.latence_ms = round((time.perf_counter() - debut) * 1000, 2)
        self.audit.write(user, role, question, answer.statut,
                         [s["ref"] for s in answer.sources], answer.latence_ms, answer.fournisseur)
        return answer

    def _answer(self, question: str, role: str) -> Answer:
        if detect_injection(question):
            return Answer(BLOQUE, "bloque", fournisseur="garde-fou")

        # Un passage n'est retenu que s'il est assez pertinent (score) ET couvre assez la question.
        hits = [(c, s) for c, s in self.retriever.search(question, groups_for(role), self.settings.top_k,
                                                          self.settings.min_coverage)
                if s >= self.settings.min_score]
        if not hits:
            return Answer(REFUS, "refus", fournisseur="recherche")

        passages = [c.texte for c, _ in hits]
        try:
            texte, fournisseur = self.llm.generate(question, passages), self.llm.name
        except Exception:
            # Le service reste disponible si le modèle de langage tombe : réponse extractive.
            texte, fournisseur = self.fallback.generate(question, passages), "extractif (secours)"

        texte = redact(texte or "").strip()        # seconde barrière, au cas où le modèle en produirait
        if not texte or _REFUS_MODELE.search(texte):
            return Answer(REFUS, "refus", fournisseur=fournisseur)

        cites = {int(n) for n in _CITATION.findall(texte)}
        if cites - set(range(1, len(hits) + 1)):
            return Answer(REFUS, "refus", fournisseur=fournisseur)   # citation d'un extrait inexistant
        numeros = cites or set(range(1, len(hits) + 1))            # sans citation : on montre tout ce qui a été lu
        sources = [{"n": i, "ref": c.ref, "document": c.doc_id, "titre": c.titre, "section": c.section}
                   for i, (c, _) in enumerate(hits, 1) if i in numeros]
        return Answer(texte, "ok", sources, fournisseur=fournisseur)
