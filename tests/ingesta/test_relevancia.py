"""Tests del filtro de relevancia por categoría raíz de VTEX."""

from observatorio.ingesta.marketplace.relevancia import categoria_raiz, es_alimento


def test_raiz_extrae_primer_segmento():
    assert categoria_raiz("Abarrotes/Arroz/Arroz Extra") == "Abarrotes"
    assert categoria_raiz("Frutas y Verduras/Verduras") == "Frutas y Verduras"
    assert categoria_raiz(None) is None
    assert categoria_raiz("") is None


def test_alimentos_pasan():
    assert es_alimento("Abarrotes/Arroz/Arroz Extra")
    assert es_alimento("Frutas y Verduras/Verduras/Cebolla")
    assert es_alimento("Carnes, Aves y Pescados/Pollo")
    assert es_alimento("Lácteos y Huevos/Huevos")  # con tilde


def test_ruido_se_descarta():
    assert not es_alimento("Limpieza/Lejía")
    assert not es_alimento("Mascotas/Comida para perros")
    assert not es_alimento("Automotriz/Cuidado del Auto")
    assert not es_alimento("Cuidado Personal y Salud/Shampoo")
    assert not es_alimento(None)


def test_comparacion_tolera_tildes_y_mayusculas():
    # aunque la raíz venga sin tilde o en otra caja, debe reconocerla
    assert es_alimento("lacteos y huevos/leche")
    assert es_alimento("PANADERÍA Y PASTELERÍA/Pan")
