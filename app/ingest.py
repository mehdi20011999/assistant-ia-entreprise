"""Chargement des documents Markdown et découpage en passages (un passage par section)."""
from dataclasses import dataclass
from pathlib import Path

REQUIRED = ("id", "titre", "departement", "acces")


@dataclass(frozen=True, slots=True)
class Chunk:
    doc_id: str
    titre: str
    section: str
    texte: str
    departement: str
    acces: frozenset

    @property
    def ref(self) -> str:
        return f"{self.doc_id}#{self.section}"


def parse_front_matter(raw: str, source: str = "document") -> tuple[dict, str]:
    if not raw.startswith("---"):
        raise ValueError(f"{source} : en-tête YAML manquant")
    try:
        _, header, body = raw.split("---", 2)
    except ValueError:
        raise ValueError(f"{source} : en-tête YAML non fermé") from None
    meta = {}
    for line in header.strip().splitlines():
        key, _, value = line.partition(":")
        value = value.strip()
        if value.startswith("[") and value.endswith("]"):
            meta[key.strip()] = [v.strip() for v in value[1:-1].split(",") if v.strip()]
        else:
            meta[key.strip()] = value
    for required in REQUIRED:
        if not meta.get(required):
            raise ValueError(f"{source} : champ obligatoire absent ou vide : {required}")
    if not isinstance(meta["acces"], list):
        # « acces: rh » sans crochets serait lu lettre par lettre : on refuse plutôt que d'ouvrir des droits au hasard.
        raise ValueError(f"{source} : « acces » doit être une liste, par exemple [rh, direction]")
    return meta, body


def split_sections(body: str) -> list[tuple[str, str]]:
    """Découpe le corps en (titre de section, texte), une entrée par titre « ## »."""
    sections, current, lines = [], None, []
    for line in body.splitlines() + ["## "]:          # sentinelle pour vider la dernière section
        if line.startswith("## "):
            texte = " ".join(x.strip() for x in lines if x.strip())
            if current and texte:
                sections.append((current, texte))
            current, lines = line[3:].strip(), []
        elif not line.startswith("# "):
            lines.append(line)
    return sections


def load_chunks(docs_dir: Path) -> list[Chunk]:
    chunks, ids = [], {}
    paths = sorted(Path(docs_dir).glob("*.md"))
    if not paths:
        raise ValueError(f"aucun document .md dans {docs_dir}")
    for path in paths:
        meta, body = parse_front_matter(path.read_text(encoding="utf-8"), path.name)
        if meta["id"] in ids:
            raise ValueError(f"{path.name} : identifiant « {meta['id']} » déjà utilisé par {ids[meta['id']]}")
        ids[meta["id"]] = path.name
        sections = split_sections(body)
        if not sections:
            raise ValueError(f"{path.name} : aucune section « ## » avec du texte")
        acces = frozenset(meta["acces"])
        chunks += [Chunk(meta["id"], meta["titre"], section, texte, meta["departement"], acces)
                   for section, texte in sections]
    return chunks
