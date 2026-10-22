"""Normalisation du texte français pour la recherche lexicale."""
import re
import unicodedata
from functools import lru_cache

STOPWORDS = frozenset("""
a au aux avec ce ces cet cette dans de des du elle en et est il ils je la le les leur leurs lui ma mais me mes mon ne
ni nos notre nous on ou par pas pour qu que qui sa se ses son sont sur ta te tes toi ton tu un une vos votre vous y
d l j m n s t c qu quel quelle quels quelles combien comment quand puis peux peut dois doit faut ai as avons avez ont
etre suis sommes etes the of and to is are what how
""".split())

_WORD = re.compile(r"[a-z0-9]+")
_SENTENCE = re.compile(r"(?<=[.!?])\s+(?=[A-ZÀ-ÖØ-Þ0-9])")


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in text if not unicodedata.combining(c))


def stem(token: str) -> str:
    """Racinisation légère : retire les terminaisons de pluriel les plus fréquentes."""
    if len(token) > 4 and token.endswith("aux"):
        return token[:-3] + "al"
    if len(token) > 3 and token.endswith(("s", "x")):
        return token[:-1]
    return token


def tokenize(text: str) -> list[str]:
    return [stem(t) for t in _WORD.findall(normalize(text)) if t not in STOPWORDS and len(t) > 1]


@lru_cache(maxsize=16384)
def token_set(text: str) -> frozenset:
    """Mots d'une phrase du corpus. Mis en cache : le corpus change rarement, les phrases reviennent souvent."""
    return frozenset(tokenize(text))


@lru_cache(maxsize=4096)
def split_sentences(text: str) -> tuple[str, ...]:
    return tuple(p.strip() for p in _SENTENCE.split(text.strip()) if p.strip())
