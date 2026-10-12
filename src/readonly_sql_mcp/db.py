"""Lock 1: the database itself refuses to change.

This lock does not trust the query analyser: it must hold even if a malicious
statement reaches it.

Read-only mode alone is not enough: it only covers the main file. ATTACH opens
any other SQLite file on disk, readable and writable. So the engine also gets
an authorizer, consulted while every statement is prepared, that allows reading
and nothing else. It is an allowlist: an action SQLite adds tomorrow is refused
until someone decides otherwise.
"""
import sqlite3
from pathlib import Path

_ALLOWED_ACTIONS = {
    sqlite3.SQLITE_SELECT,
    sqlite3.SQLITE_READ,
    sqlite3.SQLITE_FUNCTION,
    sqlite3.SQLITE_RECURSIVE,  # WITH RECURSIVE
}


def _authorizer(action, _arg1, _arg2, _db_name, _trigger):
    return sqlite3.SQLITE_OK if action in _ALLOWED_ACTIONS else sqlite3.SQLITE_DENY


def open_readonly(path: str | Path) -> sqlite3.Connection:
    uri = Path(path).resolve().as_uri() + "?mode=ro"
    con = sqlite3.connect(uri, uri=True)
    con.set_authorizer(_authorizer)
    return con
