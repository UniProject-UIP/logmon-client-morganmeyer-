"""El middleware, contra una app FastAPI de verdad.

El cliente se reemplaza por uno falso que sólo junta payloads: acá interesa qué
se registra, no cómo se envía.
"""

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from logmon_client import paso
from logmon_client.middleware import LogMonMiddleware


class ClienteFalso:
    parent_type = "API"

    def __init__(self):
        self.payloads = []

    def registrar(self, payload):
        self.payloads.append(payload)


@pytest.fixture
def cliente():
    return ClienteFalso()


@pytest.fixture
def client(cliente):
    app = FastAPI()
    app.add_middleware(LogMonMiddleware, cliente=cliente)

    @app.get("/ok")
    async def ok():
        with paso("consultando base"):
            pass
        return {"ok": True}

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    @app.get("/rompe")
    async def rompe():
        with paso("cobrando"):
            raise RuntimeError("boom")

    @app.get("/http-error")
    async def http_error():
        raise HTTPException(status_code=404, detail="no está")

    @app.get("/cinco-cientos")
    async def cinco_cientos():
        return JSONResponse({"detail": "roto"}, status_code=500)

    return TestClient(app, raise_server_exceptions=False)


def test_un_request_genera_un_log(client, cliente):
    client.get("/ok")

    assert len(cliente.payloads) == 1
    assert cliente.payloads[0]["metodo"] == "GET"
    assert cliente.payloads[0]["entrada"] == "GET /ok"


def test_los_pasos_del_handler_llegan_al_log(client, cliente):
    client.get("/ok")

    contenidos = [s["contenido"] for s in cliente.payloads[0]["steps"]]
    assert "consultando base" in contenidos


def test_la_query_string_va_en_la_entrada(client, cliente):
    client.get("/ok?pagina=2&orden=desc")

    assert cliente.payloads[0]["entrada"] == "GET /ok?pagina=2&orden=desc"


def test_las_rutas_excluidas_no_se_registran(client, cliente):
    client.get("/health")

    assert cliente.payloads == []


def test_una_excepcion_deja_el_paso_en_error(client, cliente):
    client.get("/rompe")

    steps = cliente.payloads[0]["steps"]
    errores = [s for s in steps if s["tipo"] == "ERROR"]
    assert len(errores) == 1
    assert "boom" in errores[0]["contenido"]


def test_un_404_no_se_considera_fallo_de_la_operacion(client, cliente):
    # Un 404 es una respuesta legitima, no una operacion rota.
    client.get("/http-error")

    steps = cliente.payloads[0]["steps"]
    assert all(s["tipo"] != "ERROR" for s in steps)
    assert "404" in cliente.payloads[0]["resultado"]


def test_un_500_sin_excepcion_si_es_fallo(client, cliente):
    client.get("/cinco-cientos")

    steps = cliente.payloads[0]["steps"]
    assert any(s["tipo"] == "ERROR" for s in steps)


def test_el_tiempo_total_queda_repartido_en_los_pasos(client, cliente):
    client.get("/ok")

    steps = cliente.payloads[0]["steps"]
    assert sum(s["duration_ms"] for s in steps) >= 0
    assert all(s["duration_ms"] >= 0 for s in steps)


def test_requests_seguidos_no_arrastran_pasos_del_anterior(client, cliente):
    client.get("/ok")
    client.get("/ok")

    primero = [s["contenido"] for s in cliente.payloads[0]["steps"]]
    segundo = [s["contenido"] for s in cliente.payloads[1]["steps"]]
    assert primero == segundo
    assert len(segundo) == 3  # ENTRADA + paso + respuesta
