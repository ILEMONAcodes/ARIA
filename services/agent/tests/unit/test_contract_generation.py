"""The schema freshness check must fail without rewriting a developer's files."""

import importlib.util
from pathlib import Path

import pytest


@pytest.fixture
def generator(monkeypatch, tmp_path):
    repository = Path(__file__).resolve().parents[4]
    spec = importlib.util.spec_from_file_location(
        "gen_contract", repository / "scripts" / "gen_contract.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "ROOT", tmp_path)
    monkeypatch.setattr("sys.argv", ["gen_contract.py", "--check"])
    return module


def test_schema_check_accepts_generated_contract_without_rewriting(
    generator, tmp_path, monkeypatch
):
    monkeypatch.setattr("sys.argv", ["gen_contract.py"])
    generator.main()
    path = tmp_path / "apps/desktop/src/contract/schema.json"
    before = path.stat().st_mtime_ns
    monkeypatch.setattr("sys.argv", ["gen_contract.py", "--check"])
    generator.main()
    assert path.stat().st_mtime_ns == before


@pytest.mark.parametrize("existing", [None, "{}\n"])
def test_schema_check_rejects_missing_or_stale_contract_without_writing(
    generator, tmp_path, existing
):
    path = tmp_path / "apps/desktop/src/contract/schema.json"
    if existing is not None:
        path.parent.mkdir(parents=True)
        path.write_text(existing, encoding="utf-8")
    with pytest.raises(SystemExit) as error:
        generator.main()
    assert error.value.code == 1
    if existing is None:
        assert not path.exists()
    else:
        assert path.read_text(encoding="utf-8") == existing
