import pytest

from readonly_sql_mcp.demo import build


@pytest.fixture(scope="session")
def shop_db(tmp_path_factory):
    path = tmp_path_factory.mktemp("demo") / "shop.db"
    build(path)
    return path


@pytest.fixture
def anyio_backend():
    return "asyncio"
