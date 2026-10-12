"""The server, through a real MCP client. Each lock is checked to be WIRED
behind the tools, not only correct on its own."""
import sqlite3
import sys

import pytest
from mcp import Client, StdioServerParameters

from readonly_sql_mcp import server as server_module
from readonly_sql_mcp.limits import Limits
from readonly_sql_mcp.server import build_server

pytestmark = pytest.mark.anyio

ENDLESS = "WITH RECURSIVE n(i) AS (SELECT 1 UNION ALL SELECT i + 1 FROM n) SELECT i FROM n"


def text(result) -> str:
    return " ".join(part.text for part in result.content)


def invoice_count(path) -> int:
    con = sqlite3.connect(path)
    try:
        return con.execute("SELECT count(*) FROM invoices").fetchone()[0]
    finally:
        con.close()


async def call(db, tool, arguments=None, limits=Limits()):
    async with Client(build_server(db, limits)) as client:
        return await client.call_tool(tool, arguments or {})


async def test_every_tool_is_declared_read_only(shop_db):
    async with Client(build_server(shop_db)) as client:
        tools = (await client.list_tools()).tools
    assert sorted(tool.name for tool in tools) == ["describe_table", "list_tables", "query"]
    assert all(tool.annotations.read_only_hint for tool in tools)


async def test_list_tables(shop_db):
    result = await call(shop_db, "list_tables")
    assert result.structured_content["result"] == [
        "customers", "invoice_lines", "invoices", "payments", "products"]


async def test_describe_table(shop_db):
    result = await call(shop_db, "describe_table", {"table": "invoices"})
    description = result.structured_content
    assert "REFERENCES customers" in description["create_statement"]
    assert description["row_count"] == 2000


@pytest.mark.parametrize("name", ["nope", "invoices' OR '1'='1", 'invoices"; DROP TABLE invoices; --'])
async def test_describe_unknown_table(shop_db, name):
    result = await call(shop_db, "describe_table", {"table": name})
    assert result.is_error
    assert "list_tables" in text(result)


async def test_query_answers(shop_db):
    result = await call(shop_db, "query", {"sql": "SELECT count(*) FROM invoices WHERE status = 'paid'"})
    assert result.structured_content["rows"] == [[1589]]
    assert not result.structured_content["truncated"]


async def test_sqlite_error_is_returned_to_the_agent(shop_db):
    result = await call(shop_db, "query", {"sql": "SELECT no_such_column FROM invoices"})
    assert result.is_error
    assert "no_such_column" in text(result)


# --- Lock 2 is wired: refused before reaching the engine, with its message.

async def test_write_is_refused_by_the_analyser(shop_db):
    result = await call(shop_db, "query", {"sql": "DELETE FROM invoices"})
    assert result.is_error
    assert "Only one read query is allowed" in text(result)
    assert invoice_count(shop_db) == 2000


# --- Lock 1 is wired: it holds even if lock 2 lets everything through.

async def test_engine_still_refuses_when_the_analyser_is_broken(shop_db, monkeypatch):
    monkeypatch.setattr(server_module, "check_query", lambda sql: None)
    result = await call(shop_db, "query", {"sql": "DELETE FROM invoices"})
    assert result.is_error
    assert invoice_count(shop_db) == 2000


# --- Lock 3 is wired: limits apply to tool calls.

async def test_rows_are_capped(shop_db):
    result = await call(shop_db, "query", {"sql": ENDLESS}, Limits(max_rows=10))
    assert len(result.structured_content["rows"]) == 10
    assert result.structured_content["truncated"]
    assert "first 10 rows" in result.structured_content["note"]


async def test_long_query_is_stopped(shop_db):
    slow = ("WITH RECURSIVE n(i) AS (SELECT 1 UNION ALL SELECT i + 1 FROM n WHERE i < 100000000) "
            "SELECT count(*) FROM n")
    result = await call(shop_db, "query", {"sql": slow}, Limits(timeout_seconds=0.2))
    assert result.is_error
    assert "longer than" in text(result)


# --- End to end: the real program, launched over stdio as an MCP client would.

async def test_end_to_end_over_stdio(shop_db):
    params = StdioServerParameters(command=sys.executable, args=["-m", "readonly_sql_mcp", str(shop_db)])
    async with Client(params) as client:
        tools = (await client.list_tools()).tools
        refused = await client.call_tool("query", {"sql": "DROP TABLE invoices"})
        answer = await client.call_tool("query", {"sql": "SELECT count(*) FROM customers"})
    assert len(tools) == 3
    assert refused.is_error
    assert answer.structured_content["rows"] == [[200]]
    assert invoice_count(shop_db) == 2000
