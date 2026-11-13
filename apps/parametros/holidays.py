"""
Festivos oficiales de Colombia (SPEC 07, §3.3).

Lógica pura: no importa Django ni consulta la base de datos. Aplica la Ley 51
de 1983 (Ley Emiliani): unos festivos son fijos, otros se corren al lunes
siguiente y otros dependen del Domingo de Pascua.
"""

from dataclasses import dataclass
from datetime import date, timedelta

MIN_YEAR = 1984  # primer año completo de la Ley 51 de 1983
MAX_YEAR = 2100


@dataclass(frozen=True)
class OfficialHoliday:
    code: str
    name: str
    date: date


def easter_sunday(year: int) -> date:
    """Domingo de Pascua con el algoritmo gregoriano anónimo (Meeus/Jones/Butcher)."""
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7  # noqa: E741 (nombre del algoritmo)
    m = (a + 11 * h + 22 * l) // 451
    month, day = divmod(h + l - 7 * m + 114, 31)
    return date(year, month, day + 1)


def next_monday(day: date) -> date:
    """El mismo día si es lunes; si no, el lunes siguiente."""
    return day + timedelta(days=(7 - day.weekday()) % 7)


def colombian_holidays(year: int) -> list[OfficialHoliday]:
    """
    Los 18 festivos oficiales de `year`, ordenados por fecha.

    Dos festivos pueden caer el mismo día (Sagrado Corazón y San Pedro y San
    Pablo, cuando la Pascua es tardía). Se devuelven los dos, en el orden de la
    tabla de la §3.3. Lanza `ValueError` fuera de 1984 a 2100.
    """
    if not MIN_YEAR <= year <= MAX_YEAR:
        raise ValueError(f"El año debe estar entre {MIN_YEAR} y {MAX_YEAR}: {year}.")

    easter = easter_sunday(year)

    def fixed(month: int, day: int) -> date:
        return date(year, month, day)

    def moved(month: int, day: int) -> date:
        return next_monday(date(year, month, day))

    def from_easter(days: int) -> date:
        return easter + timedelta(days=days)

    # En el orden de la tabla de la §3.3.
    holidays = [
        OfficialHoliday("ano_nuevo", "Año Nuevo", fixed(1, 1)),
        OfficialHoliday("reyes_magos", "Día de los Reyes Magos", moved(1, 6)),
        OfficialHoliday("san_jose", "Día de San José", moved(3, 19)),
        OfficialHoliday("jueves_santo", "Jueves Santo", from_easter(-3)),
        OfficialHoliday("viernes_santo", "Viernes Santo", from_easter(-2)),
        OfficialHoliday("dia_trabajo", "Día del Trabajo", fixed(5, 1)),
        OfficialHoliday("ascension", "Ascensión del Señor", from_easter(43)),
        OfficialHoliday("corpus_christi", "Corpus Christi", from_easter(64)),
        OfficialHoliday("sagrado_corazon", "Sagrado Corazón", from_easter(71)),
        OfficialHoliday("san_pedro_san_pablo", "San Pedro y San Pablo", moved(6, 29)),
        OfficialHoliday("independencia", "Día de la Independencia", fixed(7, 20)),
        OfficialHoliday("batalla_boyaca", "Batalla de Boyacá", fixed(8, 7)),
        OfficialHoliday("asuncion", "La Asunción de la Virgen", moved(8, 15)),
        OfficialHoliday("dia_raza", "Día de la Raza", moved(10, 12)),
        OfficialHoliday("todos_santos", "Día de Todos los Santos", moved(11, 1)),
        OfficialHoliday(
            "independencia_cartagena", "Independencia de Cartagena", moved(11, 11)
        ),
        OfficialHoliday(
            "inmaculada_concepcion", "Día de la Inmaculada Concepción", fixed(12, 8)
        ),
        OfficialHoliday("navidad", "Navidad", fixed(12, 25)),
    ]
    # `sorted` es estable: en un empate se conserva el orden de la tabla.
    return sorted(holidays, key=lambda holiday: holiday.date)
