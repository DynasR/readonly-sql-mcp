"""Lock 2: the query is read before anything reaches the engine.

This lock is not the guarantee (lock 1 is: the engine knows what it writes,
the analyser can only infer it). It exists for two reasons:
- refuse early, with a message the agent can act on, instead of an engine error;
- hold on engines where lock 1 is weaker or misconfigured.

It parses the SQL with a real parser, never a regex: a regex refuses
SELECT 'DELETE' and accepts WITH x AS (DELETE ...) SELECT.
"""
import sqlglot
from sqlglot import exp
from sqlglot.errors import SqlglotError


class QueryRefused(Exception):
    pass


_WHAT_IS_ALLOWED = (
    "Only one read query is allowed: SELECT, WITH ... SELECT, UNION. "
    "Nothing that writes, one statement at a time."
)

# Nodes that write, or change the session, wherever they sit in the tree:
# a read query can hide one inside a CTE (WITH x AS (DELETE ...)) or an INTO.
# This list is a backstop, not the rule: the rule is the allowlist on the root.
_WRITING_NODES = (
    exp.Insert, exp.Update, exp.Delete, exp.Merge, exp.TruncateTable,
    exp.Create, exp.Drop, exp.Alter, exp.Into,
    exp.Command, exp.Pragma, exp.Attach, exp.Detach,
    exp.Transaction, exp.Commit, exp.Rollback, exp.Set, exp.Use,
    exp.Copy, exp.Grant, exp.Revoke,
)


def check_query(sql: str, dialect: str = "sqlite") -> None:
    """Raise QueryRefused unless `sql` is exactly one read-only query."""
    try:
        statements = [s for s in sqlglot.parse(sql, read=dialect) if s is not None]
    except SqlglotError as error:
        raise QueryRefused(f"The query could not be parsed ({error}). {_WHAT_IS_ALLOWED}")

    if len(statements) != 1:
        raise QueryRefused(f"Expected one statement, got {len(statements)}. {_WHAT_IS_ALLOWED}")

    statement = statements[0]
    if not isinstance(statement, exp.Query):
        raise QueryRefused(f"{statement.key.upper()} is not a read query. {_WHAT_IS_ALLOWED}")

    for node in statement.walk():
        if isinstance(node, _WRITING_NODES):
            raise QueryRefused(
                f"The query contains {node.key.upper()}, which writes. {_WHAT_IS_ALLOWED}"
            )
