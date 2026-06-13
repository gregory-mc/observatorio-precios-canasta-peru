"""Parseo del IPC del INEI contra Excel real congelado + cobertura (issue #12).

El fixture es el archivo real publicado por el INEI (IPC Lima Metropolitana,
descarga de mayo 2026). Congela el contrato del parser: layout por posición de
columna, forward-fill del año, "Setiembre", y "-" → None en las variaciones.
"""

from pathlib import Path

from observatorio.ingesta.inei.models import IpcInei
from observatorio.ingesta.inei.parser import parsear_ipc

FIXTURE = Path(__file__).parent.parent / "fixtures" / "inei" / "ipc_lm_may26.xlsx"


def _filas() -> list[IpcInei]:
    return parsear_ipc(FIXTURE.read_bytes())


def test_parsea_fixture_real_base_dic2021():
    filas = _filas()

    assert filas, "el parser no devolvió filas"
    assert all(isinstance(f, IpcInei) for f in filas)
    assert all(f.fuente == "inei_ipc" for f in filas)
    assert all(f.ambito == "Lima Metropolitana" and f.base == "Dic2021" for f in filas)

    por_periodo = {f.periodo: f for f in filas}

    # Serie reexpresada en base 2021: arranca en enero 1994.
    primero = por_periodo["1994-01"]
    assert (primero.anio, primero.mes) == (1994, 1)
    assert round(primero.indice, 5) == 33.41605
    # Primer año sin variaciones (no hay mes previo) → None.
    assert primero.var_mensual is None
    assert primero.var_anual is None

    # Último mes publicado en este fixture (mayo 2026).
    ultimo = por_periodo["2026-05"]
    assert round(ultimo.indice, 2) == 120.02
    assert ultimo.var_anual == 3.91


def test_cobertura_contigua_sin_huecos():
    filas = _filas()
    periodos = sorted(f.periodo for f in filas)

    # Sin duplicados.
    assert len(periodos) == len(set(periodos))

    # Contigua mes a mes entre el primero y el último.
    def ym(p: str) -> int:
        anio, mes = p.split("-")
        return int(anio) * 12 + int(mes) - 1

    inicio, fin = ym(periodos[0]), ym(periodos[-1])
    esperados = set(range(inicio, fin + 1))
    assert {ym(p) for p in periodos} == esperados


def test_tipos_y_periodo():
    filas = _filas()
    f = filas[-1]
    assert isinstance(f.indice, float)
    assert isinstance(f.anio, int) and isinstance(f.mes, int)
    assert f.periodo == f"{f.anio:04d}-{f.mes:02d}"
