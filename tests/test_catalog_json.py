"""The shared gzipped JSON catalog loader and the catalog convention."""


import pytest

from custom_components.adjustable_bed.beds.ruf_richmat.models import MODEL_IDS
from custom_components.adjustable_bed.beds.ruf_richmat.profiles import profiles
from custom_components.adjustable_bed.catalog_json import CatalogError, Node
from custom_components.adjustable_bed.const import RUF_RICHMAT_APPS


@pytest.mark.parametrize(
    ("value", "read", "message"),
    [
        (True, Node.integer, "x: expected an integer, got True"),
        (1, Node.text, "x: expected a string, got 1"),
        (0, Node.flag, "x: expected a boolean, got 0"),
        ([1], lambda node: node.row(2), "x: expected a row of 2 cells"),
        ({"a": 1}, lambda node: node.record("a", "b"), "x: expected an object with members"),
        ({"a": [1.5]}, Node.json, "x.a[0]: expected a string, integer"),
    ],
)
def test_a_value_of_the_wrong_type_names_its_path(value, read, message):
    with pytest.raises(CatalogError, match=message.replace("[", r"\[").replace("]", r"\]")):
        read(Node(value, "x"))


def test_nested_values_keep_their_path():
    row = Node({"rows": [["a", 2]]}, "app.json.gz").entries()["rows"].items()[0]
    text, number = row.row(2)
    assert (text.text(), number.integer()) == ("a", 2)
    with pytest.raises(CatalogError, match=r"app.json.gz.rows\[0\]\[1\]: expected a string"):
        number.text()


@pytest.mark.parametrize("app", sorted(RUF_RICHMAT_APPS.values()))
def test_static_ruf_model_ids_match_each_validated_catalog(app):
    assert set(MODEL_IDS[app]) == set(profiles(app))


