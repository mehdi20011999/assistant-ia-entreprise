"""Garde-fous : détection d'injection de prompt et masquage des données personnelles (loi 09-08)."""
import re

INJECTION_PATTERNS = [
    r"ignor\w*\s+(toutes?\s+)?(les\s+|vos\s+|tes\s+)?(instructions|consignes|r[eè]gles)",
    r"ignore\s+(all\s+|the\s+|any\s+)?(previous|prior|above)?\s*instructions",
    r"(mode|role)\s+(administrateur|admin|d[ée]veloppeur|developer|root|dan)",
    r"system\s*prompt|prompt\s+syst[eè]me|instructions\s+syst[eè]me",
    r"tu\s+es\s+(maintenant|d[ée]sormais)|you\s+are\s+now",
    r"(r[ée]v[eè]le|affiche|donne)[\w\s-]{0,30}(confidentiel|secret|cach[ée])",
    r"jailbreak|bypass|contourne",
    r"تجاهل\s+(كل\s+|جميع\s+)?(التعليمات|الأوامر|القواعد)",          # arabe : « ignore les instructions »
    r"(نسا|خلي)\s+(كاع\s+)?(التعليمات|الأوامر|القواعد)",            # darija
]
_INJECTION = re.compile("|".join(f"(?:{p})" for p in INJECTION_PATTERNS), re.IGNORECASE)

PII_PATTERNS = [
    ("[EMAIL MASQUÉ]", re.compile(r"\b[\w.+-]+@[\w-]+(\.[\w-]+)+\b")),
    ("[RIB MASQUÉ]", re.compile(r"\b(?:MA\d{2}\s?)?(?:\d[\s]?){24}\b")),
    ("[TÉLÉPHONE MASQUÉ]", re.compile(r"(?:\+212\s?|\b0)[5-7](?:[\s.-]?\d{2}){4}\b")),
    ("[CIN MASQUÉE]", re.compile(r"\b[A-Z]{1,2}\d{5,6}\b", re.IGNORECASE)),
]


def detect_injection(question: str) -> str | None:
    match = _INJECTION.search(question)
    return match.group(0) if match else None


def redact(text: str) -> str:
    for label, pattern in PII_PATTERNS:
        text = pattern.sub(label, text)
    return text
