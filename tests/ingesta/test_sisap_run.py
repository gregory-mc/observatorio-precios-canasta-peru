"""Tests para run_ingesta_sisap: detección de día hábil y reintentos de app-level."""

from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from observatorio.ingesta.sisap.run_ingesta_sisap import (
    _solicitar_filas,
    ejecutar_ingesta_diaria,
    es_dia_habil_peru,
)

# ---------------------------------------------------------------------------
# es_dia_habil_peru
# ---------------------------------------------------------------------------


class TestEsDiaHabilPeru:
    def test_lunes_comun(self):
        assert es_dia_habil_peru(date(2026, 6, 8)) is True  # lunes

    def test_viernes_comun(self):
        assert es_dia_habil_peru(date(2026, 6, 12)) is True  # viernes

    def test_sabado_es_no_habil(self):
        assert es_dia_habil_peru(date(2026, 6, 6)) is False  # sábado

    def test_domingo_es_no_habil(self):
        assert es_dia_habil_peru(date(2026, 6, 7)) is False  # domingo

    def test_feriado_nacional_peru(self):
        # 28 de julio — Día de la Independencia del Perú
        assert es_dia_habil_peru(date(2026, 7, 28)) is False

    def test_navidad_es_no_habil(self):
        assert es_dia_habil_peru(date(2026, 12, 25)) is False

    def test_dia_laboral_no_feriado(self):
        # Miércoles cualquiera, no feriado
        assert es_dia_habil_peru(date(2026, 3, 4)) is True


# ---------------------------------------------------------------------------
# _solicitar_filas
# ---------------------------------------------------------------------------

FIXTURE_MINORISTA = "sisap_lima_minorista_2026-05-15.html"


def _html_con_datos() -> str:
    from pathlib import Path

    ruta = Path(__file__).parent.parent / "fixtures" / "sisap" / FIXTURE_MINORISTA
    return ruta.read_text(encoding="utf-8")


def _html_vacio() -> str:
    from pathlib import Path

    ruta = Path(__file__).parent.parent / "fixtures" / "sisap" / "sisap_sin_datos.html"
    return ruta.read_text(encoding="utf-8")


def _mock_response(html: str, status: int = 200) -> MagicMock:
    resp = MagicMock()
    resp.text = html
    resp.status_code = status
    resp.raise_for_status = MagicMock()
    return resp


class TestSolicitarFilas:
    def test_retorna_filas_cuando_hay_datos(self):
        session = MagicMock()
        session.get.return_value = _mock_response(_html_con_datos())

        filas = _solicitar_filas(
            session, [], fecha="2026-05-15", tipo_mercado="minorista"
        )

        assert filas is not None
        assert len(filas) == 93
        session.get.assert_called_once()

    def test_reintenta_si_tabla_vacia_y_luego_tiene_datos(self):
        session = MagicMock()
        session.get.side_effect = [
            _mock_response(_html_vacio()),
            _mock_response(_html_con_datos()),
        ]

        with patch("observatorio.ingesta.sisap.run_ingesta_sisap.time.sleep") as mock_sleep:
            filas = _solicitar_filas(
                session, [], fecha="2026-05-15", tipo_mercado="minorista"
            )

        assert filas is not None and len(filas) > 0
        assert session.get.call_count == 2
        mock_sleep.assert_called_once()

    def test_retorna_lista_vacia_tras_agotar_reintentos(self):
        session = MagicMock()
        # Siempre responde vacío
        session.get.return_value = _mock_response(_html_vacio())

        with patch("observatorio.ingesta.sisap.run_ingesta_sisap.time.sleep"):
            filas = _solicitar_filas(
                session, [], fecha="2026-06-11", tipo_mercado="minorista"
            )

        assert filas == []
        # 1 intento inicial + 2 reintentos = 3 llamadas
        assert session.get.call_count == 3

    def test_retorna_none_en_error_de_red(self):
        import requests

        session = MagicMock()
        session.get.side_effect = requests.exceptions.ConnectionError("sin red")

        filas = _solicitar_filas(
            session, [], fecha="2026-06-11", tipo_mercado="minorista"
        )

        assert filas is None
        session.get.assert_called_once()


# ---------------------------------------------------------------------------
# ejecutar_ingesta_diaria — semántica de alerta (issue #80)
# ---------------------------------------------------------------------------


def _fila_con_precio() -> MagicMock:
    fila = MagicMock()
    fila.precio_prom = 5.0
    fila.producto = "Papa"
    return fila


def _ejecutar_con_mercados(monkeypatch, *, minorista, mayorista):
    """Corre ejecutar_ingesta_diaria mockeando red, día hábil y efectos de I/O.

    `minorista`/`mayorista` son el valor que devuelve _solicitar_filas para cada
    mercado (lista de filas, [] para tabla vacía, o None para error de red).
    """
    mod = "observatorio.ingesta.sisap.run_ingesta_sisap"
    monkeypatch.setattr(f"{mod}.es_dia_habil_peru", lambda _fecha: True)
    monkeypatch.setattr(f"{mod}.escribir_csv", lambda *a, **k: None)
    monkeypatch.setattr(f"{mod}.subir_a_r2", lambda *a, **k: None)
    monkeypatch.setattr(f"{mod}.configurar_sesion_resiliente", lambda: MagicMock())
    # TIPOS_MERCADO se itera en orden: minorista, luego mayorista
    monkeypatch.setattr(f"{mod}._solicitar_filas", MagicMock(side_effect=[minorista, mayorista]))
    monkeypatch.delenv("SIMULAR_FALLO", raising=False)
    ejecutar_ingesta_diaria()


class TestSemanticaAlerta:
    def test_un_mercado_vacio_y_otro_carga_no_alerta(self, monkeypatch):
        # Caso del issue #80: minorista interdiario (vacío) pero mayorista carga.
        _ejecutar_con_mercados(monkeypatch, minorista=[], mayorista=[_fila_con_precio()])
        # No debe terminar con sys.exit(1)

    def test_ambos_mercados_cargan_no_alerta(self, monkeypatch):
        _ejecutar_con_mercados(
            monkeypatch, minorista=[_fila_con_precio()], mayorista=[_fila_con_precio()]
        )

    def test_error_de_red_en_un_mercado_alerta(self, monkeypatch):
        with pytest.raises(SystemExit) as exc:
            _ejecutar_con_mercados(monkeypatch, minorista=None, mayorista=[_fila_con_precio()])
        assert exc.value.code == 1

    def test_todos_los_mercados_vacios_alerta(self, monkeypatch):
        with pytest.raises(SystemExit) as exc:
            _ejecutar_con_mercados(monkeypatch, minorista=[], mayorista=[])
        assert exc.value.code == 1
