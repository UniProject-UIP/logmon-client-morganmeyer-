"""El payload tiene que cumplir el contrato de LogCreate."""

import time

from logmon_client.contexto import ERROR, SALIDA, Operacion
from logmon_client.payload import construir

CLAVES = {"parent_type", "entrada", "resultado", "metodo", "fecha", "steps"}


def _op(pasos=()):
    op = Operacion(metodo="POST", entrada="POST /pedidos", inicio=time.perf_counter())
    for descripcion, tipo, dur in pasos:
        op.anotar(descripcion, tipo, dur)
    return op


def test_no_manda_los_campos_que_deriva_el_servidor():
    payload = construir(_op(), "API", total_ms=10, resultado="HTTP 201")

    # source_id lo agrega el cliente al resolver el nombre de la fuente.
    assert set(payload) == CLAVES
    assert "id" not in payload
    assert "estado" not in payload
    assert "tiempo_ms" not in payload


def test_el_primer_paso_es_la_entrada():
    payload = construir(_op(), "API", total_ms=10, resultado="HTTP 201")

    assert payload["steps"][0]["tipo"] == "ENTRADA"
    assert payload["steps"][0]["contenido"] == "POST /pedidos"


def test_los_pasos_van_numerados_sin_huecos():
    payload = construir(
        _op([("uno", SALIDA, 5), ("dos", SALIDA, 7)]), "API", total_ms=30, resultado="ok"
    )

    assert [s["orden"] for s in payload["steps"]] == [1, 2, 3, 4]


def test_la_suma_de_duraciones_es_el_tiempo_real_del_request():
    # Es la propiedad que hace util el tiempo_ms que deriva LogMon: el paso
    # final absorbe lo que no quedo atribuido a ningun paso intermedio.
    payload = construir(
        _op([("a", SALIDA, 30), ("b", SALIDA, 20)]), "API", total_ms=100, resultado="ok"
    )

    assert sum(s["duration_ms"] for s in payload["steps"]) == 100


def test_si_los_pasos_ya_superan_el_total_no_hay_duracion_negativa():
    payload = construir(
        _op([("a", SALIDA, 90)]), "API", total_ms=50, resultado="ok"
    )

    assert all(s["duration_ms"] >= 0 for s in payload["steps"])


def test_sin_pasos_igual_sale_un_log_valido():
    payload = construir(_op(), "API", total_ms=42, resultado="HTTP 200")

    assert len(payload["steps"]) == 2  # ENTRADA + respuesta
    assert sum(s["duration_ms"] for s in payload["steps"]) == 42


def test_un_fallo_fuera_de_un_paso_agrega_el_paso_error():
    payload = construir(
        _op(), "API", total_ms=10, resultado="HTTP 500", fallo="RuntimeError: boom"
    )

    assert payload["steps"][-1]["tipo"] == ERROR
    assert payload["resultado"] == "RuntimeError: boom"


def test_si_un_paso_ya_fallo_no_se_duplica_el_error():
    payload = construir(
        _op([("cobrando", ERROR, 5)]),
        "API",
        total_ms=10,
        resultado="HTTP 500",
        fallo="HTTPException",
    )

    errores = [s for s in payload["steps"] if s["tipo"] == ERROR]
    assert len(errores) == 1
    assert errores[0]["contenido"] == "cobrando"
