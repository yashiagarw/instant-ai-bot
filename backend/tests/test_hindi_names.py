"""Phase 5.5: reviewed Hindi fault names on the result (name_hi), never machine-translated."""

from sqlalchemy import select

from app.diagnosis import service
from app.knowledge.models import CustomerPhrase, Fault
from tests.test_datasets import live, world  # noqa: F401 - fixtures


def test_only_approved_devanagari_phrases_become_hindi_names(db_session, world):  # noqa: F811
    a, b, c = db_session.scalars(select(Fault).limit(3)).all()
    db_session.add_all([
        CustomerPhrase(fault_id=a.id, text="बैटरी बार बार बैठ जाती है", language="hi", source="real", status="approved"),
        CustomerPhrase(fault_id=a.id, text="बैटरी बैठ गई", language="hi", source="real", status="approved"),
        CustomerPhrase(fault_id=b.id, text="बैटरी खराब", language="hi", source="real", status="draft"),  # not reviewed
        CustomerPhrase(fault_id=b.id, text="battery baith gayi", language="hi", source="real", status="approved"),
        CustomerPhrase(fault_id=c.id, text="gaadi start nahi ho rahi", language="hinglish", source="real",
                       status="approved"),
    ])  # fmt: skip
    db_session.flush()
    names = service.hindi_names(db_session, [a.id, b.id, c.id])
    assert names == {a.id: "बैटरी बैठ गई"}  # the shortest reviewed one; Hinglish / drafts never
    assert service.hindi_names(db_session, []) == {}
