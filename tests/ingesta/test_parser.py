"""Tests del aplanado de productos VTEX. El fixture replica la forma real
de la respuesta de Marketplace (campos verificados contra la API)."""

from observatorio.ingesta.marketplace.parser import aplanar

PRODUCTO = {
    "productId": "101190089",
    "productName": "Arroz Extra Añejo Premium FARAÓN Bolsa 10Kg",
    "brand": "FARAON",
    "categories": ["/Abarrotes/Arroz/Arroz Extra/", "/Abarrotes/Arroz/", "/Abarrotes/"],
    "link": "https://www.plazavea.com.pe/arroz-extra-anejo-premium-faraon-bolsa-10-kg/p",
    "items": [
        {
            "itemId": "11566644",
            "name": "Arroz Extra Añejo Premium FARAÓN Bolsa 10Kg",
            "nameComplete": "Arroz Extra Añejo Premium FARAÓN Bolsa 10Kg",
            "ean": "7750182000000",
            "measurementUnit": "un",
            "unitMultiplier": 1.0,
            "sellers": [
                {
                    "sellerName": "Marketplace",
                    "commertialOffer": {
                        "Price": 46.3,
                        "ListPrice": 47.9,
                        "IsAvailable": True,
                        "AvailableQuantity": 64,
                    },
                }
            ],
        }
    ],
}


def test_aplanar_extrae_precio_y_unidad():
    filas = aplanar(PRODUCTO, fecha_captura="2026-05-26", consulta="texto:arroz")
    assert len(filas) == 1
    fila = filas[0]
    assert fila.product_id == "101190089"
    assert fila.sku_id == "11566644"
    assert fila.unidad_medida == "un"
    assert fila.multiplicador_unidad == 1.0
    assert fila.precio == 46.3
    assert fila.precio_lista == 47.9
    assert fila.disponible is True
    assert fila.cantidad_disponible == 64
    assert fila.categoria == "Abarrotes/Arroz/Arroz Extra"
    assert fila.fuente == "marketplace"
    assert fila.consulta == "texto:arroz"


def test_aplanar_sku_sin_oferta_no_revienta():
    producto = {
        "productId": "1",
        "productName": "Sin stock",
        "items": [{"itemId": "9", "measurementUnit": "kg", "unitMultiplier": 1.0, "sellers": []}],
    }
    filas = aplanar(producto, fecha_captura="2026-05-26", consulta="texto:x")
    assert len(filas) == 1
    assert filas[0].precio is None
    assert filas[0].disponible is False
    assert filas[0].cantidad_disponible == 0


def test_aplanar_multiples_skus():
    producto = {
        "productId": "2",
        "productName": "Multi",
        "items": [
            {"itemId": "a", "measurementUnit": "un", "unitMultiplier": 1.0, "sellers": []},
            {"itemId": "b", "measurementUnit": "un", "unitMultiplier": 1.0, "sellers": []},
        ],
    }
    filas = aplanar(producto, fecha_captura="2026-05-26", consulta="ids:2")
    assert {f.sku_id for f in filas} == {"a", "b"}
