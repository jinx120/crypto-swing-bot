import os

from swingbot.selftest.expectations import EXPECTATIONS, GUIDE_AFFORDANCES, Expectation

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def test_catalog_is_keyed_consistently():
    for key, exp in EXPECTATIONS.items():
        assert isinstance(exp, Expectation)
        assert exp.key == key
        assert exp.session and exp.expected and exp.doc and exp.section
        assert exp.fix_bias in ("doc", "ui")


def test_every_doc_ref_points_at_existing_file():
    docs = {e.doc for e in EXPECTATIONS.values()}
    docs |= {"frontend/src/guide.md"}
    for doc in docs:
        assert os.path.isfile(os.path.join(_ROOT, doc)), f"missing doc: {doc}"


def test_guide_affordances_shape():
    assert len(GUIDE_AFFORDANCES) >= 5
    for text, route, section in GUIDE_AFFORDANCES:
        assert text and route.startswith("/#/") and section.startswith("§")
