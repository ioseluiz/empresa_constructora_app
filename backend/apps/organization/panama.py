"""Datos de referencia de Panamá: feriados nacionales, provincias y catálogos iniciales.

⚠️ Validar con asesoría laboral panameña. Las reglas viven aquí y en datos editables por la
empresa (los feriados generados se pueden corregir o complementar con días decretados).
"""

from datetime import date, timedelta


def easter_sunday(year: int) -> date:
    """Domingo de Pascua (algoritmo gregoriano anónimo de Meeus/Jones/Butcher)."""
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    ell = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * ell) // 451
    month, day = divmod(h + ell - 7 * m + 114, 31)
    return date(year, month, day + 1)


def national_holidays(year: int) -> list[tuple[date, str, str]]:
    """(fecha, nombre, tipo) de los días de fiesta y duelo nacional (Código de Trabajo, art. 46,
    y leyes posteriores). No aplica traslados: si un decreto mueve un feriado, se edita."""
    easter = easter_sunday(year)
    return [
        (date(year, 1, 1), "Año Nuevo", "national"),
        (date(year, 1, 9), "Día de los Mártires", "mourning"),
        (easter - timedelta(days=47), "Martes de Carnaval", "national"),
        (easter - timedelta(days=2), "Viernes Santo", "national"),
        (date(year, 5, 1), "Día del Trabajador", "national"),
        (date(year, 11, 3), "Separación de Panamá de Colombia", "national"),
        (date(year, 11, 5), "Día de Colón", "national"),
        (date(year, 11, 10), "Primer Grito de Independencia (Villa de Los Santos)", "national"),
        (date(year, 11, 28), "Independencia de Panamá de España", "national"),
        (date(year, 12, 8), "Día de las Madres", "national"),
        (date(year, 12, 20), "Día de Duelo Nacional", "mourning"),
        (date(year, 12, 25), "Navidad", "national"),
    ]


PROVINCES = [
    ("bocas_del_toro", "Bocas del Toro"),
    ("cocle", "Coclé"),
    ("colon", "Colón"),
    ("chiriqui", "Chiriquí"),
    ("darien", "Darién"),
    ("herrera", "Herrera"),
    ("los_santos", "Los Santos"),
    ("panama", "Panamá"),
    ("panama_oeste", "Panamá Oeste"),
    ("veraguas", "Veraguas"),
    ("guna_yala", "Comarca Guna Yala"),
    ("embera_wounaan", "Comarca Emberá-Wounaan"),
    ("ngabe_bugle", "Comarca Ngäbe-Buglé"),
    ("naso_tjer_di", "Comarca Naso Tjër Di"),
]

# Categorías habituales de la convención SUNTRACS–CAPAC. Las tarifas NO se precargan:
# deben ingresarse desde la convención vigente.
CBA_CATEGORIES = [
    ("AYU", "Ayudante general"),
    ("ALB", "Albañil"),
    ("CAR", "Carpintero"),
    ("ARM", "Armador (fierrero)"),
    ("ELE", "Electricista"),
    ("PLO", "Plomero"),
    ("SOL", "Soldador"),
    ("PIN", "Pintor"),
    ("OPP", "Operador de equipo pesado"),
    ("OPL", "Operador de equipo liviano"),
    ("CAP", "Capataz"),
]

# (código, nombre, área, código de categoría de convención)
POSITIONS = [
    ("AYU", "Ayudante general", "field", "AYU"),
    ("ALB", "Albañil", "field", "ALB"),
    ("CAR", "Carpintero", "field", "CAR"),
    ("ARM", "Armador", "field", "ARM"),
    ("ELE", "Electricista", "field", "ELE"),
    ("PLO", "Plomero", "field", "PLO"),
    ("SOL", "Soldador", "field", "SOL"),
    ("PIN", "Pintor", "field", "PIN"),
    ("OPP", "Operador de equipo pesado", "field", "OPP"),
    ("CAP", "Capataz", "field", "CAP"),
    ("MDO", "Maestro de obra", "field", None),
    ("ING", "Ingeniero residente", "field", None),
    ("BOD", "Bodeguero", "field", None),
    ("ADM", "Asistente administrativo", "office", None),
    ("CON", "Contador", "office", None),
    ("RRH", "Analista de recursos humanos", "office", None),
    ("GER", "Gerente", "office", None),
]

# Bancos con servicio ACH en Panamá (código interno, nombre). El código de ruta ACH de cada
# banco se configurará con el archivo de pago (Sprint 10).
BANKS = [
    ("banco_general", "Banco General"),
    ("banistmo", "Banistmo"),
    ("bac", "BAC Credomatic"),
    ("banconal", "Banco Nacional de Panamá"),
    ("caja_ahorros", "Caja de Ahorros"),
    ("global_bank", "Global Bank"),
    ("multibank", "Multibank"),
    ("banesco", "Banesco"),
    ("davivienda", "Davivienda"),
    ("credicorp", "Credicorp Bank"),
    ("scotiabank", "Scotiabank"),
    ("banco_aliado", "Banco Aliado"),
    ("st_georges", "St. Georges Bank"),
    ("towerbank", "Towerbank"),
    ("banisi", "Banisi"),
    ("other", "Otro"),
]

# Cédula panameña: provincia (1-13) o letra (E extranjero, N naturalizado, PE panameño nacido
# en el extranjero), con sufijo opcional AV (antes de la vigencia) o PI (comarca indígena),
# seguida de tomo y asiento. Ej.: 8-123-4567, 4PI-12-345, E-8-123456.
CEDULA_REGEX = r"^(?:(?:[1-9]|1[0-3])(?:AV|PI)?|PE|E|N)-\d{1,4}-\d{1,6}$"
