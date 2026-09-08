"""Unit tests for MongoDB Store namespace identity encoding."""

from agent.stores.mongodb_store import MongoDBStore


def test_namespace_path_uses_full_namespace_identity():
    namespace_a = MongoDBStore._namespace_path(("users", "user-a", "skills"))
    namespace_b = MongoDBStore._namespace_path(("users", "user-b", "skills"))

    assert namespace_a == '["users","user-a","skills"]'
    assert namespace_b == '["users","user-b","skills"]'
    assert namespace_a != namespace_b


def test_namespace_path_has_no_delimiter_ambiguity():
    assert MongoDBStore._namespace_path(("a/b", "c")) != MongoDBStore._namespace_path(
        ("a", "b/c")
    )
