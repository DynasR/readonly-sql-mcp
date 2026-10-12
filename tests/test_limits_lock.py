"""Lock 3 must hold ALONE: these tests use a plain connection, with neither
lock 1 nor lock 2. Locks 1 and 2 stop writes; lock 3 stops a read that is
too big or too long from hurting the agent or the database."""
import sqlite3
import time

import pytest

from readonly_sql_mcp.limits import Limits, QueryTooBig, QueryTimeout, run_limited

# Counts forever: without a limit, it never returns.
ENDLESS = "WITH RECURSIVE n(i) AS (SELECT 1 UNION ALL SELECT i + 1 FROM n) SELECT i FROM n"
# Returns one row, after a long time (seconds to minutes without a limit).
SLOW = (
    "WITH RECURSIVE n(i) AS (SELECT 1 UNION ALL SELECT i + 1 FROM n WHERE i < 100000000) "
    "SELECT count(*) FROM n"
)


@pytest.fixture
def con():
    con = sqlite3.connect(":memory:")
    con.execute("CREATE TABLE t (x INTEGER)")
    con.executemany("INSERT INTO t VALUES (?)", [(i,) for i in range(10)])
    return con


def test_small_result_is_returned_whole(con):
    """Control: a lock that refuses everything would pass every test below."""
    result = run_limited(con, "SELECT x FROM t ORDER BY x", Limits())
    assert result.columns == ["x"]
    assert result.rows == [(i,) for i in range(10)]
    assert not result.truncated


def test_rows_beyond_the_limit_are_never_read(con):
    """The endless query returns at once: only max_rows + 1 rows are read."""
    result = run_limited(con, ENDLESS, Limits(max_rows=5))
    assert result.rows == [(1,), (2,), (3,), (4,), (5,)]
    assert result.truncated


def test_exactly_max_rows_is_not_truncated(con):
    result = run_limited(con, "SELECT x FROM t", Limits(max_rows=10))
    assert len(result.rows) == 10
    assert not result.truncated


def test_a_long_query_is_stopped(con):
    start = time.monotonic()
    with pytest.raises(QueryTimeout):
        run_limited(con, SLOW, Limits(timeout_seconds=0.2))
    assert time.monotonic() - start < 2


def test_the_connection_is_usable_after_a_timeout(con):
    """The timer must be disarmed: the next query must not inherit it."""
    with pytest.raises(QueryTimeout):
        run_limited(con, SLOW, Limits(timeout_seconds=0.2))
    time.sleep(0.3)
    # The engine only consults the timer every few thousand instructions: a
    # tiny query would finish before it, and a timer left armed would go
    # unseen. This one is long enough to meet it, and still takes milliseconds.
    assert con.execute(
        "WITH RECURSIVE n(i) AS (SELECT 1 UNION ALL SELECT i + 1 FROM n WHERE i < 10000) "
        "SELECT count(*) FROM n"
    ).fetchone() == (10000,)


def test_one_giant_value_is_refused(con):
    """One row, but 10 MB: the row limit does not see it."""
    with pytest.raises(QueryTooBig):
        run_limited(con, "SELECT zeroblob(10000000)", Limits(max_value_bytes=100_000))


def test_size_limit_does_not_outlive_the_query(con):
    with pytest.raises(QueryTooBig):
        run_limited(con, "SELECT zeroblob(10000000)", Limits(max_value_bytes=100_000))
    assert len(con.execute("SELECT zeroblob(10000000)").fetchone()[0]) == 10_000_000
