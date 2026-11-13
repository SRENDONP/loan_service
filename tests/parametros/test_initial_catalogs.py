"""Pruebas de la carga inicial de catálogos y festivos (SPEC 07, §3.4).

Usan la base de pruebas normal, donde las migraciones de datos ya corrieron.
"""

from datetime import date

import pytest

from apps.parametros.models import (
    CreditPurpose,
    DocumentType,
    Holiday,
    HolidayOrigin,
    Occupation,
    RejectionReason,
    ThirdPartyRelationType,
    VoidReason,
)

pytestmark = pytest.mark.django_db

EXPECTED = {
    DocumentType: ["CC", "CE", "PPT", "PA", "TI"],
    Occupation: [
        "COMERCIANTE",
        "TENDERO",
        "VENDEDOR_AMBULANTE",
        "EMPLEADO",
        "INDEPENDIENTE",
        "TRANSPORTADOR",
        "AMA_DE_CASA",
        "OTRA",
    ],
    CreditPurpose: [
        "CAPITAL_TRABAJO",
        "COMPRA_MERCANCIA",
        "GASTOS_PERSONALES",
        "VIVIENDA",
        "SALUD",
        "EDUCACION",
        "PAGO_DEUDAS",
        "OTRO",
    ],
    VoidReason: [
        "ERROR_DIGITACION",
        "PAGO_DUPLICADO",
        "VALOR_INCORRECTO",
        "CREDITO_EQUIVOCADO",
        "OTRO",
    ],
    RejectionReason: [
        "CAPACIDAD_PAGO",
        "REFERENCIAS_NO_VERIFICADAS",
        "DOCUMENTACION_INCOMPLETA",
        "HISTORIAL_MORA",
        "OTRO",
    ],
    ThirdPartyRelationType: ["CODEUDOR", "REFERENCIA_PERSONAL", "FAMILIAR", "OTRO"],
}


# Catálogos


@pytest.mark.parametrize("model", list(EXPECTED))
def test_each_catalog_has_exactly_its_items_active_and_in_order(model):
    items = list(model.objects.all())

    assert [item.code for item in items] == EXPECTED[model]
    assert [item.display_order for item in items] == [
        10 * position for position in range(1, len(items) + 1)
    ]
    assert all(item.is_active for item in items)
    assert all(item.updated_by is None for item in items)


def test_names_of_some_items():
    assert DocumentType.objects.get(code="PPT").name == (
        "Permiso por protección temporal"
    )
    assert CreditPurpose.objects.get(code="COMPRA_MERCANCIA").name == (
        "Compra de mercancía"
    )
    assert RejectionReason.objects.get(code="CAPACIDAD_PAGO").name == (
        "Capacidad de pago insuficiente"
    )


def test_document_type_codes_match_the_fixed_user_list():
    from apps.accounts.models import DocumentType as UserDocumentType

    assert set(EXPECTED[DocumentType]) == set(UserDocumentType.values)


def test_only_codebtor_and_personal_reference_are_system_items():
    system = [
        (model, item.code)
        for model in EXPECTED
        for item in model.objects.filter(is_system=True)
    ]

    assert system == [
        (ThirdPartyRelationType, "CODEUDOR"),
        (ThirdPartyRelationType, "REFERENCIA_PERSONAL"),
    ]


# Festivos


def test_90_official_holidays_18_per_year_from_2026_to_2030():
    official = Holiday.objects.filter(origin=HolidayOrigin.OFFICIAL)

    assert official.count() == 90
    for year in range(2026, 2031):
        assert official.filter(official_year=year).count() == 18
    assert not Holiday.objects.filter(origin=HolidayOrigin.CUSTOM).exists()


def test_official_holidays_of_2026_are_active_with_their_dates():
    holidays = Holiday.objects.filter(official_year=2026)

    assert all(holiday.is_active for holiday in holidays)
    assert holidays.get(official_code="reyes_magos").date == date(2026, 1, 12)
    assert holidays.get(official_code="reyes_magos").name == ("Día de los Reyes Magos")


def test_coincidence_of_2030_keeps_only_the_first_holiday_active():
    same_day = Holiday.objects.filter(date=date(2030, 7, 1)).order_by("pk")

    assert [(h.official_code, h.is_active) for h in same_day] == [
        ("sagrado_corazon", True),
        ("san_pedro_san_pablo", False),
    ]
    assert Holiday.objects.filter(official_year=2030, is_active=True).count() == 17


def test_no_holidays_outside_the_initial_years():
    assert not Holiday.objects.exclude(official_year__range=(2026, 2030)).exists()
