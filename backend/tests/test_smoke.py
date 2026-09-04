def test_health(client):
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_product_lookup_survives_a_numeric_looking_code(api, make_product):
    make_product(price="100.00", stock=1)

    assert api.get("/api/menu/products/²").status_code == 404
    assert api.get("/api/menu/products/₅").status_code == 404
