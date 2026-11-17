"""El motor es lógica pura (constitución §5.2, SPEC 09 §3.1)."""

import ast
from pathlib import Path

import pytest
from django.apps import apps as django_apps

import apps.amortizacion

APP_DIR = Path(apps.amortizacion.__file__).parent
FORBIDDEN_ROOTS = {"django", "apps"}


def _modules() -> list[Path]:
    return sorted(path for path in APP_DIR.rglob("*.py") if path.name != "apps.py")


def _absolute_imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0:
            imported.add(node.module or "")
    return imported


def test_there_are_modules_to_check():
    assert any(path.name == "types.py" for path in _modules())


@pytest.mark.parametrize("path", _modules(), ids=lambda path: path.name)
def test_module_does_not_import_django_nor_project_apps(path):
    roots = {name.split(".")[0] for name in _absolute_imports(path)}

    assert not roots & FORBIDDEN_ROOTS


def test_detects_forbidden_import(tmp_path):
    module = tmp_path / "bad.py"
    module.write_text("from django.db import models\nimport apps.parametros\n")

    roots = {name.split(".")[0] for name in _absolute_imports(module)}

    assert roots & FORBIDDEN_ROOTS == {"django", "apps"}


def test_app_is_installed_without_models_views_or_urls():
    config = django_apps.get_app_config("amortizacion")

    assert config.name == "apps.amortizacion"
    assert list(config.get_models()) == []
    for name in ("models.py", "views.py", "urls.py", "migrations"):
        assert not (APP_DIR / name).exists()
