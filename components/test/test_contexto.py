"""El registro de pasos y su aislamiento entre requests concurrentes."""

import asyncio

import pytest

from logmon_client import anotar, paso
from logmon_client.contexto import ERROR, SALIDA, abrir, actual, cerrar


@pytest.fixture(autouse=True)
def _sin_operacion():
    cerrar()
    yield
    cerrar()


def test_paso_registra_descripcion_y_duracion():
    op = abrir("GET", "GET /x")

    with paso("consultando base"):
        pass

    assert len(op.pasos) == 1
    assert op.pasos[0].descripcion == "consultando base"
    assert op.pasos[0].tipo == SALIDA
    assert op.pasos[0].duration_ms >= 0


def test_una_excepcion_marca_el_paso_como_error_y_se_vuelve_a_lanzar():
    op = abrir("POST", "POST /pagos")

    with pytest.raises(ValueError):
        with paso("cobrando"):
            raise ValueError("sin fondos")

    assert op.pasos[0].tipo == ERROR
    assert "sin fondos" in op.pasos[0].descripcion
    assert op.tiene_error


def test_fuera_de_una_operacion_paso_no_hace_nada():
    # Instrumentar no debe obligar a cambiar como se ejecuta el codigo: el
    # mismo servicio tiene que poder correr en un script o en un test.
    with paso("suelto"):
        pass

    assert actual() is None


def test_fuera_de_una_operacion_paso_no_se_traga_la_excepcion():
    with pytest.raises(ValueError):
        with paso("suelto"):
            raise ValueError("boom")


def test_anotar_registra_un_paso_instantaneo():
    op = abrir("GET", "GET /x")

    anotar("cache hit")

    assert op.pasos[0].descripcion == "cache hit"
    assert op.pasos[0].duration_ms == 0


@pytest.mark.anyio
async def test_dos_operaciones_concurrentes_no_mezclan_sus_pasos():
    resultados = {}

    async def operar(nombre, cuantos):
        op = abrir("GET", f"GET /{nombre}")
        for i in range(cuantos):
            with paso(f"{nombre}-{i}"):
                await asyncio.sleep(0.01)
        resultados[nombre] = [p.descripcion for p in op.pasos]

    await asyncio.gather(operar("a", 3), operar("b", 2))

    assert resultados["a"] == ["a-0", "a-1", "a-2"]
    assert resultados["b"] == ["b-0", "b-1"]


@pytest.fixture
def anyio_backend():
    return "asyncio"
