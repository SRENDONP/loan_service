"""Pruebas de los recursos estáticos y de las reglas de la plantilla (SPEC 02)."""

import re
from pathlib import Path

import pytest
from django.conf import settings
from django.contrib.staticfiles import finders

TEMPLATES_DIR = Path(settings.BASE_DIR) / "templates"
STATIC_TAG = re.compile(r"""\{%\s*static\s+['"]([^'"]+)['"]\s*%\}""")

DATATABLES_ASSETS = {
    "vendor/datatables/dataTables.bootstrap4.min.css",
    "vendor/datatables/jquery.dataTables.min.js",
    "vendor/datatables/dataTables.bootstrap4.min.js",
}


def read_template(name: str) -> str:
    return (TEMPLATES_DIR / name).read_text(encoding="utf-8")


def static_paths(name: str) -> set[str]:
    return set(STATIC_TAG.findall(read_template(name)))


def all_templates() -> list[Path]:
    return sorted(TEMPLATES_DIR.rglob("*.html"))


@pytest.mark.parametrize("template", ["base.html", "includes/datatable.html"])
def test_every_static_file_loaded_by_layout_exists(template):
    paths = static_paths(template)

    assert paths, f"{template} no carga recursos con {{% static %}}"
    missing = [path for path in sorted(paths) if finders.find(path) is None]
    assert missing == []


def test_datatable_include_names_all_datatables_assets():
    assert static_paths("includes/datatable.html") == DATATABLES_ASSETS


def test_every_static_file_in_any_template_exists():
    missing = {
        f"{template.relative_to(TEMPLATES_DIR)}: {path}"
        for template in all_templates()
        for path in STATIC_TAG.findall(template.read_text(encoding="utf-8"))
        if finders.find(path) is None
    }
    assert missing == set()


def test_no_template_links_to_references():
    offenders = [
        str(template.relative_to(TEMPLATES_DIR))
        for template in all_templates()
        if "references/" in template.read_text(encoding="utf-8")
    ]
    assert offenders == []


@pytest.mark.parametrize("template", ["base.html", "500.html"])
def test_app_css_loads_after_sb_admin_css(template):
    html = read_template(template)

    sb_admin = html.index("{% static 'css/sb-admin-2.min.css' %}")
    app = html.index("{% static 'css/app.css' %}")
    assert sb_admin < app


def test_app_js_loads_after_template_scripts():
    html = read_template("base.html")

    order = [
        html.index("{% static 'vendor/jquery/jquery.min.js' %}"),
        html.index("{% static 'vendor/bootstrap/js/bootstrap.bundle.min.js' %}"),
        html.index("{% static 'js/sb-admin-2.min.js' %}"),
        html.index("{% static 'js/app.js' %}"),
    ]
    assert order == sorted(order)


def test_font_awesome_webfonts_resolve_from_css():
    """all.min.css busca sus fuentes en ../webfonts/; deben existir ahí."""
    css_path = finders.find("vendor/fontawesome-free/css/all.min.css")
    css = Path(css_path).read_text(encoding="utf-8")
    fonts = set(re.findall(r"url\(\.\./webfonts/([^)?#]+)", css))

    assert fonts
    missing = [
        font
        for font in sorted(fonts)
        if finders.find(f"vendor/fontawesome-free/webfonts/{font}") is None
    ]
    assert missing == []
