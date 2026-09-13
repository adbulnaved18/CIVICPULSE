"""Regression tests for the real migration commit helper, with no network access."""
from unittest.mock import MagicMock

import pytest

from scripts.migrate_sqlite_to_postgres import commit_migration


@pytest.mark.parametrize("lookup", ["present", "absent", "unavailable"])
def test_uncertain_commit_never_deletes_images(lookup):
    transaction = MagicMock()
    transaction.commit.side_effect = ConnectionError("lost commit acknowledgement")
    engine = MagicMock()
    conn = engine.connect.return_value.__enter__.return_value
    if lookup == "unavailable":
        engine.connect.side_effect = ConnectionError("database unavailable")
    else:
        conn.execute.return_value.fetchone.return_value = (42,) if lookup == "present" else None
    storage = MagicMock()
    with pytest.raises(RuntimeError, match="not confirmed"):
        commit_migration(transaction, engine, storage, ["evidence/run/image"])
    storage.delete_evidence.assert_not_called()
    storage.record_recovery_task.assert_called_once()
    details = storage.record_recovery_task.call_args.args[1]
    assert details["keys"] == ["evidence/run/image"]
    assert details["referenced_keys"] == (
        ["evidence/run/image"] if lookup == "present" else [] if lookup == "absent" else None
    )
    if lookup != "unavailable":
        assert conn.execute.call_args.args[1] == {"key": "evidence/run/image"}


def test_successful_commit_needs_no_recovery():
    transaction, engine, storage = MagicMock(), MagicMock(), MagicMock()
    commit_migration(transaction, engine, storage, ["evidence/run/image"])
    transaction.commit.assert_called_once()
    engine.connect.assert_not_called()
    storage.delete_evidence.assert_not_called()
    storage.record_recovery_task.assert_not_called()
