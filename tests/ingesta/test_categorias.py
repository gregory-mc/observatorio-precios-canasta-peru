"""Tests de la planificación de navegación de categorías (lógica de descenso
cuando una categoría excede el tope de paginación). Sin red: se inyecta el
contador como función."""

from observatorio.ingesta.marketplace.categorias import planificar


def test_no_desciende_si_cabe():
    nodos = [{"id": 77, "name": "Frutas y Verduras", "children": [{"id": 1, "name": "Verduras"}]}]
    assert planificar(nodos, lambda fq: 500) == [("C:77", "Frutas y Verduras")]


def test_desciende_si_excede_el_tope():
    nodos = [
        {
            "id": 431,
            "name": "Abarrotes",
            "children": [{"id": 432, "name": "Arroz"}, {"id": 433, "name": "Aceite"}],
        }
    ]
    obj = planificar(nodos, lambda fq: 3000 if fq == "C:431" else 100)
    assert ("C:431/432", "Abarrotes/Arroz") in obj
    assert ("C:431/433", "Abarrotes/Aceite") in obj
    assert all(fq != "C:431" for fq, _ in obj)  # la raíz grande no se navega entera


def test_capea_si_excede_pero_no_hay_hijos():
    nodos = [{"id": 431, "name": "Abarrotes", "children": []}]
    # sin hijos no hay cómo bajar: se navega entera (la paginación la capeará)
    assert planificar(nodos, lambda fq: 3000) == [("C:431", "Abarrotes")]
