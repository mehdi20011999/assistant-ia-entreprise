import pytest

from app.config import groups_for, load_settings
from app.ingest import load_chunks, parse_front_matter
from app.retriever import BM25Retriever


@pytest.fixture(scope="module")
def retriever():
    return BM25Retriever(load_chunks(load_settings().docs_dir))


def test_front_matter_valide():
    meta, body = parse_front_matter("---\nid: x\ntitre: T\ndepartement: RH\nacces: [rh, direction]\n---\n# T\n")
    assert meta["acces"] == ["rh", "direction"] and "# T" in body


def test_front_matter_incomplet_refuse():
    with pytest.raises(ValueError):
        parse_front_matter("---\nid: x\n---\ntexte")


def test_bon_document_en_tete(retriever):
    hits = retriever.search("plafond hôtel Rabat note de frais", groups_for("employe"))
    assert hits[0][0].doc_id == "finance-notes-de-frais"


def test_controle_acces_avant_classement(retriever):
    for chunk, _ in retriever.search("grille salaire ingénieur junior", groups_for("employe"), k=10):
        assert chunk.doc_id != "rh-salaires"
    assert retriever.search("grille salaire ingénieur junior", groups_for("rh"))[0][0].doc_id == "rh-salaires"


def test_documents_visibles_par_role(retriever):
    employe = {d["id"] for d in retriever.visible_documents(groups_for("employe"))}
    rh = {d["id"] for d in retriever.visible_documents(groups_for("rh"))}
    it = {d["id"] for d in retriever.visible_documents(groups_for("it"))}
    assert "rh-salaires" not in employe and "rh-salaires" in rh
    assert "it-procedures-admin" not in employe and "it-procedures-admin" not in rh
    assert {"rh-conges", "it-procedures-admin"} <= it          # l'IT est aussi un salarié
