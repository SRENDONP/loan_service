"""
Registro de los catálogos de texto (SPEC 07, §3.5).

Las vistas, las URL, el menú y los permisos se arman recorriendo `CATALOGS`.
Un catálogo nuevo es una subclase de `CatalogItem`, su migración y una línea
aquí.
"""

from dataclasses import dataclass

from django.utils.functional import Promise
from django.utils.translation import gettext_lazy as _

from apps.parametros.models import (
    CatalogItem,
    CreditPurpose,
    DocumentType,
    Occupation,
    RejectionReason,
    ThirdPartyRelationType,
    VoidReason,
)

# Códigos de los ítems de sistema de Tipos de relación de terceros (§3.4). Las
# specs de terceros y de créditos buscan estos ítems con `get_item_by_code`.
RELATION_CODEBTOR = "CODEUDOR"
RELATION_PERSONAL_REFERENCE = "REFERENCIA_PERSONAL"


@dataclass(frozen=True)
class Catalog:
    slug: str  # parte de la URL
    model: type[CatalogItem]
    label: str | Promise  # "Tipos de documento", para el título y el menú
    order: int  # posición en el submenú

    def permission(self, action: str) -> str:
        """El permiso `parametros.<action>_<modelo>` de este catálogo."""
        return f"{self.model._meta.app_label}.{action}_{self.model._meta.model_name}"

    @property
    def list_url_name(self) -> str:
        """
        El nombre de la ruta del listado, propio de cada catálogo.

        El menú resuelve sus entradas con `reverse(url_name)`, sin argumentos, y
        marca la activa por ese nombre. Por eso cada listado tiene su ruta con
        nombre, aunque la URL siga siendo `catalogos/<slug>/`.
        """
        return "parametros:catalog_" + self.slug.replace("-", "_")


CATALOGS: tuple[Catalog, ...] = (
    Catalog("tipos-documento", DocumentType, _("Tipos de documento"), 10),
    Catalog("ocupaciones", Occupation, _("Ocupaciones"), 20),
    Catalog("destinos-credito", CreditPurpose, _("Destinos de crédito"), 30),
    Catalog("motivos-anulacion", VoidReason, _("Motivos de anulación"), 40),
    Catalog("motivos-rechazo", RejectionReason, _("Motivos de rechazo"), 50),
    Catalog(
        "tipos-relacion",
        ThirdPartyRelationType,
        _("Tipos de relación de terceros"),
        60,
    ),
)

_BY_SLUG = {catalog.slug: catalog for catalog in CATALOGS}


def get_catalog(slug: str) -> Catalog:
    """El catálogo de ese `slug`. Lanza `KeyError` si no existe."""
    return _BY_SLUG[slug]
