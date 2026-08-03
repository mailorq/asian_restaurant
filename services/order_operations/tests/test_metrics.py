import urllib.request

from prometheus_client import start_http_server

from operations.metrics import projection_events


def test_metrics_endpoint_serves_projection_counter():
    projection_events.labels("orders.order.created.v1", "applied").inc()
    server, _thread = start_http_server(0)
    try:
        port = server.server_port
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/metrics", timeout=5) as resp:
            assert resp.status == 200
            body = resp.read().decode()
    finally:
        server.shutdown()
    assert "operations_projection_events_total" in body
