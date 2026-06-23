"""Navegador headless de Facilito (OSINERGMIN) con Playwright.

Facilito gatea cada consulta de precios con reCAPTCHA v3: al cargar la página,
un script mina un token (``grecaptcha.execute``) y lo deja en el campo oculto
``g-recaptcha-response``; recién entonces el formulario puede enviarse. Un POST
sin token válido redirige a ``errorRecaptcha.jsp``. Por eso esta ingesta NO usa
``requests`` como SISAP/Marketplace: necesita un navegador real que ejecute ese
JS. La parte de parseo sí es HTML puro y vive en ``parser.py`` (testeable sin red).

Flujo del formulario (verificado en junio 2026), todo sobre el mismo ``form``:
    1. GET buscadorEESS.jsp  → el JS mina el token.
    2. makeAction(<depCod>)  → POST method=inicio → página de resultados del
       departamento, con los <select> de provincia y producto poblados.
    3. set provincia + producto, cambiarProducto() → POST con el token vigente →
       devuelve la tabla ``#tblPreciosAutomotor`` con TODOS los grifos de esa
       provincia para ese producto (server-rendered; DataTables solo pagina en el
       navegador, por eso se lee la respuesta cruda y no el DOM ya paginado).

Se reabre el buscador por cada departamento: aísla fallos y garantiza un token
fresco y la función ``makeAction`` disponible.
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import TYPE_CHECKING

from .config import URL_BUSCADOR, USER_AGENT, VALORES_VACIOS

if TYPE_CHECKING:
    from collections.abc import Iterator

    from playwright.sync_api import Page

log = logging.getLogger("osinergmin")

# Espera (ms) a que el JS de reCAPTCHA deje el token en el campo oculto.
_TIMEOUT_TOKEN_MS = 30_000
# Espera (ms) a que el POST del formulario navegue a la página de resultados.
_TIMEOUT_NAV_MS = 60_000

_JS_TOKEN_LISTO = (
    "() => { const e = document.getElementById('g-recaptcha-response');"
    " return !!(e && e.value && e.value.length > 20); }"
)


class RecaptchaRechazado(RuntimeError):
    """Facilito redirigió a errorRecaptcha.jsp — el token no fue aceptado."""


class SesionFacilito:
    """Sesión de navegación sobre Facilito. Usar como context manager.

    Ejemplo:
        with SesionFacilito() as fac:
            for cod_dep, nombre_dep in DEPARTAMENTOS.items():
                provincias = fac.abrir_departamento(cod_dep)
                for cod_prov, nombre_prov in provincias:
                    html = fac.consultar(cod_prov, "126")
                    ...
    """

    def __init__(self, *, headless: bool = True) -> None:
        self._headless = headless
        self._pw = None
        self._browser = None
        self._page: Page | None = None

    def __enter__(self) -> SesionFacilito:
        from playwright.sync_api import sync_playwright

        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(headless=self._headless)
        ctx = self._browser.new_context(user_agent=USER_AGENT, locale="es-PE")
        self._page = ctx.new_page()
        return self

    def __exit__(self, *exc) -> None:
        try:
            if self._browser is not None:
                self._browser.close()
        finally:
            if self._pw is not None:
                self._pw.stop()

    # -- internos ----------------------------------------------------------- #
    @property
    def page(self) -> Page:
        if self._page is None:
            raise RuntimeError("SesionFacilito no inicializada (usar 'with').")
        return self._page

    def _esperar_token(self) -> None:
        """Espera a que reCAPTCHA mine el token. No falla si no llega a tiempo:
        el POST posterior lo delatará (redirección a errorRecaptcha)."""
        try:
            self.page.wait_for_function(_JS_TOKEN_LISTO, timeout=_TIMEOUT_TOKEN_MS)
        except Exception:  # noqa: BLE001 — timeout de Playwright
            log.warning("token reCAPTCHA no minado a tiempo; se intenta de todos modos")

    def _comprobar_recaptcha(self) -> None:
        if "errorRecaptcha" in self.page.url:
            raise RecaptchaRechazado(self.page.url)

    # -- API ---------------------------------------------------------------- #
    def abrir_departamento(self, cod_departamento: str) -> list[tuple[str, str]]:
        """Abre el buscador y selecciona el departamento.

        Devuelve la lista de provincias [(codigo, nombre)] de ese departamento,
        leídas en vivo del <select> (no se hardcodean).
        """
        page = self.page
        page.goto(URL_BUSCADOR, wait_until="networkidle", timeout=_TIMEOUT_NAV_MS)
        self._esperar_token()

        with page.expect_navigation(wait_until="networkidle", timeout=_TIMEOUT_NAV_MS):
            page.evaluate("(cod) => window.makeAction(Number(cod))", cod_departamento)
        self._comprobar_recaptcha()
        self._esperar_token()

        provincias = page.evaluate(
            "() => [...document.forms[0].provincia.options].map(o => [o.value, o.text])"
        )
        return [(str(v), t.strip()) for v, t in provincias if str(v) not in VALORES_VACIOS]

    def consultar(self, cod_provincia: str, cod_producto: str) -> str:
        """Consulta una provincia × producto y devuelve el HTML crudo de resultados.

        Requiere haber llamado antes a ``abrir_departamento``. El distrito se deja
        sin elegir → la respuesta trae todos los grifos de la provincia.
        """
        page = self.page
        with page.expect_navigation(wait_until="networkidle", timeout=_TIMEOUT_NAV_MS) as nav:
            page.evaluate(
                "([prov, prod]) => {"
                " const f = document.forms[0];"
                " f.provincia.value = prov; f.producto.value = prod;"
                " window.cambiarProducto(); }",
                [cod_provincia, cod_producto],
            )
        self._comprobar_recaptcha()
        respuesta = nav.value
        html = respuesta.text() if respuesta is not None else page.content()
        self._esperar_token()
        return html


@contextmanager
def abrir_sesion(*, headless: bool = True) -> Iterator[SesionFacilito]:
    """Alias funcional de SesionFacilito para quien prefiera ``with abrir_sesion()``."""
    with SesionFacilito(headless=headless) as sesion:
        yield sesion
