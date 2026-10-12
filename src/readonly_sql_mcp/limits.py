"""Lock 3: a read that is too big or too long is stopped.

Locks 1 and 2 stop writes. This one protects the agent (its memory, its
context window) and the database (other users) from a read that is
legitimate but excessive. Each limit is enforced by the engine while the
query runs, never by inspecting the SQL beforehand.
"""
import sqlite3
import time
from dataclasses import dataclass


@dataclass(frozen=True)
class Limits:
    max_rows: int = 200
    timeout_seconds: float = 5.0
    max_value_bytes: int = 100_000


@dataclass(frozen=True)
class Result:
    columns: list[str]
    rows: list[tuple]
    truncated: bool


class QueryTimeout(Exception):
    pass


class QueryTooBig(Exception):
    pass


# The engine calls the timer every N virtual machine instructions. Small
# enough to stop within milliseconds, large enough to cost nothing.
_CHECK_EVERY = 1_000


def run_limited(con: sqlite3.Connection, sql: str, limits: Limits) -> Result:
    deadline = time.monotonic() + limits.timeout_seconds
    con.set_progress_handler(lambda: time.monotonic() > deadline, _CHECK_EVERY)
    previous_length = con.setlimit(sqlite3.SQLITE_LIMIT_LENGTH, limits.max_value_bytes)
    try:
        cursor = con.execute(sql)
        # One row more than allowed tells us the result was cut, without
        # ever reading the rest.
        rows = cursor.fetchmany(limits.max_rows + 1)
        columns = [column[0] for column in cursor.description or []]
        cursor.close()
    except sqlite3.Error as error:
        code = getattr(error, "sqlite_errorcode", None)
        if code == sqlite3.SQLITE_INTERRUPT:
            raise QueryTimeout(
                f"The query took longer than {limits.timeout_seconds:g} s and was stopped. "
                "Narrow it with WHERE or LIMIT, or aggregate."
            ) from error
        if code == sqlite3.SQLITE_TOOBIG:
            raise QueryTooBig(
                f"A value in the result is larger than {limits.max_value_bytes} bytes. "
                "Select a shorter expression, for example substr(column, 1, 200)."
            ) from error
        raise
    finally:
        con.set_progress_handler(None, 0)
        con.setlimit(sqlite3.SQLITE_LIMIT_LENGTH, previous_length)

    return Result(columns=columns, rows=rows[: limits.max_rows], truncated=len(rows) > limits.max_rows)
