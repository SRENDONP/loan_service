"""Pruebas del registro único de parámetros globales (SPEC 06, §3.1 y §3.2)."""

from datetime import time

import pytest
from django.contrib.auth.models import Group, Permission
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, connection, transaction

from apps.accounts import roles
from apps.accounts.roles import ROLE_PERMISSIONS, Role
from apps.parametros.models import (
    RANGES,
    DateFormat,
    GlobalSettings,
    RoundingMode,
    ShiftRule,
    Weekday,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def row() -> GlobalSettings:
    return GlobalSettings.objects.get(pk=1)


def errors_of(instance: GlobalSettings) -> dict[str, list[str]]:
    with pytest.raises(ValidationError) as excinfo:
        instance.full_clean()
    return excinfo.value.message_dict


# Fila única


def test_migrate_creates_exactly_one_row_with_defaults(row):
    assert GlobalSettings.objects.count() == 1
    assert row.pk == 1
    assert row.business_name == "Gestión de préstamos"
    assert row.brand_icon == "fas fa-hand-holding-usd"
    assert row.currency_code == "COP"
    assert row.currency_symbol == "$"
    assert row.currency_decimals == 0
    assert row.date_format == DateFormat.DMY_SLASH
    assert row.collection_weekdays == [1, 2, 3, 4, 5, 6]
    assert row.collection_start_time == time(6, 0)
    assert row.collection_end_time == time(20, 0)
    assert row.non_business_weekdays == [Weekday.SUNDAY]
    assert row.holiday_shift_rule == ShiftRule.CASCADE
    assert row.rounding_multiple == 50
    assert row.rounding_mode == RoundingMode.HALF_UP
    assert row.max_failed_attempts == 5
    assert row.lockout_minutes == 15
    assert row.password_min_length == 8
    assert row.password_reset_timeout_minutes == 60
    assert row.session_idle_timeout_minutes == 30
    assert row.session_max_hours == 12
    assert row.updated_by is None


def test_defaults_pass_full_clean(row):
    row.full_clean()


def test_save_always_uses_pk_1():
    other = GlobalSettings(pk=2, business_name="Otro")
    other.save()

    assert other.pk == 1
    assert GlobalSettings.objects.count() == 1
    assert GlobalSettings.objects.get().business_name == "Otro"


def test_second_row_by_orm_fails_with_singleton_constraint():
    with pytest.raises(IntegrityError, match="parametros_globalsettings_singleton"):
        with transaction.atomic():
            GlobalSettings.objects.bulk_create([GlobalSettings(pk=2)])


def test_second_row_by_sql_fails_with_singleton_constraint(row):
    columns = [
        f.column
        for f in GlobalSettings._meta.concrete_fields
        if f.column not in ("id", "updated_by_id")
    ]
    table = GlobalSettings._meta.db_table
    with pytest.raises(IntegrityError, match="parametros_globalsettings_singleton"):
        with transaction.atomic(), connection.cursor() as cursor:
            cursor.execute(
                f"INSERT INTO {table} (id, {', '.join(columns)}) "  # noqa: S608
                f"SELECT 2, {', '.join(columns)} FROM {table} WHERE id = 1"
            )


def test_delete_is_rejected_and_row_stays(row):
    with pytest.raises(PermissionDenied):
        row.delete()

    assert GlobalSettings.objects.filter(pk=1).exists()


def test_only_view_and_change_permissions_exist():
    codenames = set(
        Permission.objects.filter(
            content_type__app_label="parametros",
            content_type__model="globalsettings",
        ).values_list("codename", flat=True)
    )

    assert codenames == {"view_globalsettings", "change_globalsettings"}


def test_str():
    assert str(GlobalSettings()) == "Parámetros globales"


# Rangos


@pytest.mark.parametrize("field", list(RANGES))
def test_range_accepts_both_ends(row, field):
    low, high = RANGES[field]
    # La inactividad debe ser menor que la duración máxima: se deja la máxima
    # en 24 horas para probar solo el rango.
    row.session_max_hours = 24
    for value in (low, high):
        setattr(row, field, value)
        if field == "session_max_hours":
            row.session_idle_timeout_minutes = 5
        row.full_clean()


@pytest.mark.parametrize("field", list(RANGES))
def test_range_rejects_just_outside(row, field):
    low, high = RANGES[field]
    row.session_max_hours = 24
    for value in (low - 1, high + 1):
        setattr(row, field, value)
        if field == "session_max_hours":
            row.session_idle_timeout_minutes = 5
        assert field in errors_of(row)


@pytest.mark.parametrize("field", list(RANGES))
def test_range_is_enforced_by_the_database(row, field):
    low, _ = RANGES[field]
    with pytest.raises(
        IntegrityError, match=f"parametros_globalsettings_{field}_range"
    ):
        with transaction.atomic():
            GlobalSettings.objects.filter(pk=1).update(**{field: low - 1})


# Reglas entre campos


def test_requires_at_least_one_collection_day(row):
    row.collection_weekdays = []

    assert "collection_weekdays" in errors_of(row)


@pytest.mark.parametrize("start", [time(20, 0), time(21, 0)])
def test_start_time_must_be_before_end_time(row, start):
    row.collection_start_time = start
    row.collection_end_time = time(20, 0)

    assert errors_of(row)["collection_end_time"] == [
        "La hora de inicio debe ser anterior a la de fin."
    ]


def test_seven_non_business_days_are_rejected(row):
    row.non_business_weekdays = list(Weekday.values)

    assert errors_of(row)["non_business_weekdays"] == [
        "Debe haber al menos un día hábil."
    ]


def test_no_non_business_days_is_allowed(row):
    row.non_business_weekdays = []

    row.full_clean()


def test_collection_day_may_also_be_non_business(row):
    row.collection_weekdays = [Weekday.SUNDAY]
    row.non_business_weekdays = [Weekday.SUNDAY]

    row.full_clean()


def test_idle_timeout_must_be_less_than_max_duration(row):
    row.session_idle_timeout_minutes = 60
    row.session_max_hours = 1

    assert errors_of(row)["session_idle_timeout_minutes"] == [
        "La inactividad debe ser menor que la duración máxima."
    ]


def test_business_name_is_stripped_and_required(row):
    row.business_name = "   "

    assert errors_of(row)["business_name"] == ["Escribe el nombre del negocio."]

    row.business_name = "  Créditos Ya  "
    row.full_clean()
    assert row.business_name == "Créditos Ya"


@pytest.mark.parametrize("code", ["CO", "COPS", "C0P", "ÑÑÑ", ""])
def test_currency_code_must_be_three_letters(row, code):
    row.currency_code = code

    assert "currency_code" in errors_of(row)


def test_currency_code_is_uppercased(row):
    row.currency_code = "usd"

    row.full_clean()

    assert row.currency_code == "USD"


def test_currency_symbol_is_required(row):
    row.currency_symbol = "  "

    assert "currency_symbol" in errors_of(row)


def test_brand_icon_must_be_from_the_list(row):
    row.brand_icon = "fas fa-skull onmouseover"

    assert "brand_icon" in errors_of(row)


def test_rounding_multiple_must_be_from_the_list(row):
    row.rounding_multiple = 333

    assert "rounding_multiple" in errors_of(row)


def test_weekdays_must_be_valid(row):
    row.collection_weekdays = [0, 8]

    assert "collection_weekdays" in errors_of(row)


# sync_roles (ADR-002)


def test_parametros_is_the_last_app_with_models():
    # El receptor de sync_roles corre con la señal de la última app con
    # modelos, que ahora es parametros.
    assert roles._last_app_with_models().label == "parametros"


def test_migrate_still_syncs_the_four_roles():
    # La base de pruebas se crea con migrate sobre una base vacía.
    for role in Role:
        perms = {
            f"{app}.{codename}"
            for app, codename in Group.objects.get(
                name=role.value
            ).permissions.values_list("content_type__app_label", "codename")
        }
        assert perms == ROLE_PERMISSIONS[role]
