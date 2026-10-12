"""Lock 1 must hold ALONE: every statement here bypasses the query analyser
and goes straight to the connection, as if the analyser had a bug."""
import sqlite3

import pytest

from readonly_sql_mcp.db import open_readonly


@pytest.fixture
def main_db(tmp_path):
    path = tmp_path / "main.db"
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE t (x INTEGER)")
    con.execute("INSERT INTO t VALUES (1)")
    con.commit()
    con.close()
    return path


@pytest.fixture
def other_db(tmp_path):
    """Another SQLite file on the same disk, that the agent must never reach."""
    path = tmp_path / "secret.db"
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE s (password TEXT)")
    con.execute("INSERT INTO s VALUES ('hunter2')")
    con.commit()
    con.close()
    return path


@pytest.mark.parametrize("sql", [
    "INSERT INTO t VALUES (2)",
    "UPDATE t SET x = 3",
    "DELETE FROM t",
    "DROP TABLE t",
    "CREATE TABLE u (y)",
    "PRAGMA query_only = 0",
])
def test_writes_on_main_file_are_refused(main_db, sql):
    con = open_readonly(main_db)
    with pytest.raises(sqlite3.Error):
        con.execute(sql)


def test_reading_still_works(main_db):
    """Control: a lock that refuses everything would pass every test above."""
    con = open_readonly(main_db)
    assert con.execute("SELECT x FROM t").fetchall() == [(1,)]
    assert con.execute(
        "WITH RECURSIVE n(i) AS (SELECT 1 UNION ALL SELECT i + 1 FROM n WHERE i < 3) "
        "SELECT count(*) FROM n"
    ).fetchall() == [(3,)]


def test_attach_cannot_reach_another_file(main_db, other_db):
    """Read-only mode only covers the main file: ATTACH opens any other
    SQLite file on disk, readable AND writable. Found by attacking lock 1."""
    con = open_readonly(main_db)
    with pytest.raises(sqlite3.Error):
        con.execute(f"ATTACH DATABASE '{other_db}' AS o")
    assert _password_unchanged(other_db)


def _password_unchanged(path):
    con = sqlite3.connect(path)
    try:
        return con.execute("SELECT password FROM s").fetchall() == [("hunter2",)]
    finally:
        con.close()
