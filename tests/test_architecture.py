import ast
from pathlib import Path

CORE = Path(__file__).resolve().parents[1] / "src" / "signal_app" / "core"
FORBIDDEN = {"fastapi", "confluent_kafka", "psycopg", "psycopg_pool", "redis"}


def imported_roots(path: Path):
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Import):
            for a in node.names:
                yield a.name.split(".")[0]
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            yield node.module.split(".")[0]


def test_core_does_not_import_frameworks_or_drivers():
    files = list(CORE.glob("*.py"))
    assert files
    bad = {f.name: sorted(set(imported_roots(f)) & FORBIDDEN) for f in files}
    assert {k: v for k, v in bad.items() if v} == {}


def test_core_does_not_import_adapters():
    for f in CORE.glob("*.py"):
        for node in ast.walk(ast.parse(f.read_text())):
            if isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                assert not mod.startswith(("adapters", "entrypoints")), f.name
                assert node.level < 2 or not mod.startswith(("adapters", "entrypoints", "shared")), f.name
