"""Lock 2 must hold ALONE: these tests never open a database. The analyser
decides from the SQL text only, before anything reaches the engine."""
import pytest

from readonly_sql_mcp.guard import QueryRefused, check_query

REFUSED = {
    # Starts with WITH, ends with SELECT: a "does it end in SELECT?" check lets
    # it through, and Postgres deletes the table.
    "write hidden in a CTE": "WITH x AS (DELETE FROM clients RETURNING *) SELECT * FROM x",
    # Postgres: SELECT ... INTO creates a new table.
    "select into": "SELECT * INTO backup FROM clients",
    "second statement": "SELECT 1; DROP TABLE t",
    "insert": "INSERT INTO t VALUES (1)",
    "update": "UPDATE t SET x = 1",
    "delete": "DELETE FROM t",
    "drop": "DROP TABLE t",
    "create": "CREATE TABLE u (y)",
    "attach": "ATTACH DATABASE 'other.db' AS o",
    "pragma": "PRAGMA query_only = 0",
    "vacuum into": "VACUUM INTO 'copy.db'",
    "replace": "REPLACE INTO t VALUES (1)",
    # Statements that write but that the backstop list of writing nodes does
    # not know: only the allowlist on the root stops them.
    "analyze (writes statistics)": "ANALYZE t",
    "reindex (rebuilds indexes)": "REINDEX t",
    "load data": "LOAD DATA INPATH 'x' INTO TABLE t",
    "empty": "   ",
    "only a comment": "-- nothing here",
    "garbage": "SELEKT * FRUM t",
}

ACCEPTED = {
    "simple": "SELECT 1",
    "lowercase": "select x from t",
    "trailing semicolon": "SELECT x FROM t;",
    # A regex looking for DELETE or ';' would refuse these honest queries.
    "write keyword inside a string": "SELECT 'DELETE FROM t' AS text",
    "semicolon inside a string": "SELECT ';DROP TABLE t' AS text",
    "join and group by": "SELECT a.name, count(*) FROM a JOIN b ON a.id = b.a_id GROUP BY a.name",
    "cte": "WITH top AS (SELECT x FROM t ORDER BY x DESC LIMIT 3) SELECT * FROM top",
    "union": "SELECT x FROM t UNION SELECT y FROM u",
    "window": "SELECT x, rank() OVER (ORDER BY x) FROM t",
}


@pytest.mark.parametrize("sql", REFUSED.values(), ids=REFUSED.keys())
def test_refused(sql):
    with pytest.raises(QueryRefused):
        check_query(sql)


@pytest.mark.parametrize("sql", ACCEPTED.values(), ids=ACCEPTED.keys())
def test_accepted(sql):
    check_query(sql)


def test_refusal_tells_the_agent_what_to_do():
    """The agent reads the message and retries: it must say what is allowed."""
    with pytest.raises(QueryRefused) as refusal:
        check_query("DELETE FROM t")
    assert "SELECT" in str(refusal.value)
