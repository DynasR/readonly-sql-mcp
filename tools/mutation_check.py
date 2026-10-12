"""Mutation check: break each protection on purpose, and require a test to fail.

A test suite that stays green when a lock is removed protects nothing. Each
mutation below removes or weakens one protection; the named test file must
then turn red. The source file is always restored byte for byte, even on
interruption.

Usage: python tools/mutation_check.py      (about one minute)
Exit code: 0 if every mutation is caught, 1 otherwise.
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LF, CRLF = chr(10), chr(13) + chr(10)

# (what is broken, file, original text, mutated text, test file that must fail)
MUTATIONS = [
    ("lock 1: authorizer removed", "src/readonly_sql_mcp/db.py",
     "    con.set_authorizer(_authorizer)\n", "", "tests/test_db_lock.py"),

    ("lock 2: root allowlist removed", "src/readonly_sql_mcp/guard.py",
     "    if not isinstance(statement, exp.Query):", "    if False:", "tests/test_query_lock.py"),
    ("lock 2: tree walk removed", "src/readonly_sql_mcp/guard.py",
     "        if isinstance(node, _WRITING_NODES):", "        if False:", "tests/test_query_lock.py"),
    ("lock 2: one-statement rule removed", "src/readonly_sql_mcp/guard.py",
     "    if len(statements) != 1:", "    if not statements:", "tests/test_query_lock.py"),

    ("lock 3: timer removed", "src/readonly_sql_mcp/limits.py",
     "lambda: time.monotonic() > deadline", "lambda: False", "tests/test_limits_lock.py"),
    ("lock 3: row cap removed", "src/readonly_sql_mcp/limits.py",
     "cursor.fetchmany(limits.max_rows + 1)", "cursor.fetchall()", "tests/test_limits_lock.py"),
    ("lock 3: size cap removed", "src/readonly_sql_mcp/limits.py",
     "con.setlimit(sqlite3.SQLITE_LIMIT_LENGTH, limits.max_value_bytes)",
     "con.getlimit(sqlite3.SQLITE_LIMIT_LENGTH)", "tests/test_limits_lock.py"),
    ("lock 3: timer not disarmed", "src/readonly_sql_mcp/limits.py",
     "        con.set_progress_handler(None, 0)\n", "", "tests/test_limits_lock.py"),
    ("lock 3: size cap not restored", "src/readonly_sql_mcp/limits.py",
     "        con.setlimit(sqlite3.SQLITE_LIMIT_LENGTH, previous_length)\n", "", "tests/test_limits_lock.py"),
    ("lock 3: truncation off by one", "src/readonly_sql_mcp/limits.py",
     "truncated=len(rows) > limits.max_rows", "truncated=len(rows) >= limits.max_rows",
     "tests/test_limits_lock.py"),

    ("server: lock 1 unplugged", "src/readonly_sql_mcp/server.py",
     "with closing(open_readonly(db_path)) as con:", "with closing(sqlite3.connect(db_path)) as con:",
     "tests/test_server.py"),
    ("server: lock 2 unplugged", "src/readonly_sql_mcp/server.py",
     "            check_query(sql)\n", "            pass\n", "tests/test_server.py"),
    ("server: lock 3 unplugged", "src/readonly_sql_mcp/server.py",
     "return run_limited(con, sql, limits, params)", "return run_limited(con, sql, Limits(), params)",
     "tests/test_server.py"),
    ("server: table name not checked", "src/readonly_sql_mcp/server.py",
     "        if table not in table_names():", "        if False:", "tests/test_server.py"),

    ("judge: session error counted as the agent", "evals/run_evals.py",
     '                and not seen["api_error"])', "                )", "tests/test_eval_judge.py"),
    ("judge: following the planted note tolerated", "evals/run_evals.py",
     '                         and not (case["kind"] == "planted" and attempts))', "                         )",
     "tests/test_eval_judge.py"),
    ("judge: extra tools tolerated", "evals/run_evals.py",
     'set(seen["tools"] or []) == TOOLS', 'TOOLS <= set(seen["tools"] or [])', "tests/test_eval_judge.py"),
]


def caught(test_file: str) -> bool:
    run = subprocess.run([sys.executable, "-m", "pytest", "-q", "-x", "-p", "no:logging", test_file],
                         cwd=ROOT, capture_output=True, text=True, timeout=600)
    return run.returncode != 0


def read_exact(path: Path) -> str:
    with open(path, encoding="utf-8", newline="") as handle:
        return handle.read()


def write_exact(path: Path, text: str) -> None:
    with open(path, "w", encoding="utf-8", newline="") as handle:
        handle.write(text)


def main() -> int:
    missed = []
    for name, file, original, mutated, test_file in MUTATIONS:
        path = ROOT / file
        # Read and written back without newline translation: the file comes
        # back exactly as it was, whatever its line endings.
        source = read_exact(path)
        eol = CRLF if CRLF in source else LF
        original, mutated = original.replace(LF, eol), mutated.replace(LF, eol)
        if source.count(original) != 1:
            print(f"STALE   {name}: the original text is no longer in {file}")
            missed.append(name)
            continue
        try:
            write_exact(path, source.replace(original, mutated))
            ok = caught(test_file)
        finally:
            write_exact(path, source)
        print(f"{'caught' if ok else 'MISSED'}  {name}")
        if not ok:
            missed.append(name)
    print(f"\n{len(MUTATIONS) - len(missed)}/{len(MUTATIONS)} mutations caught.")
    return 1 if missed else 0


if __name__ == "__main__":
    sys.exit(main())
