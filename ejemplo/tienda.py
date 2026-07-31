"""App de ejemplo: una tienda con cuatro operaciones, instrumentada.

Es una app normal de FastAPI. Lo único que agrega LogMon son tres líneas: el
import, el cliente y `instrumentar(app)`. Los `with paso(...)` son opcionales,
pero son lo que convierte un log plano en una operación con su desglose.

Para correrla:

    make ejemplo

y despues generar trafico:

    curl localhost:9000/pedidos -X POST -H 'Content-Type: application/json' -d '{"cliente":42,"items":3}'
    curl localhost:9000/clientes/42
    curl localhost:9000/pagos -X POST -H 'Content-Type: application/json' -d '{"pedido":1,"monto":99.9}'
"""

import asyncio
import random

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from logmon_client import LogMon, paso

app = FastAPI(title="Tienda de ejemplo")

logmon = LogMon(base_url="http://localhost:8000", fuente="ventas", parent_type="API")
logmon.instrumentar(app)


class PedidoIn(BaseModel):
    cliente: int
    items: int = 1


class PagoIn(BaseModel):
    pedido: int
    monto: float


async def _trabajo(minimo: float = 0.01, maximo: float = 0.08) -> None:
    """Simula el tiempo que tardaría una consulta o una llamada externa."""

    await asyncio.sleep(random.uniform(minimo, maximo))


@app.post("/pedidos")
async def crear_pedido(pedido: PedidoIn):
    with paso("Validando token de sesión"):
        await _trabajo()

    with paso(f"Verificando stock de {pedido.items} artículos"):
        await _trabajo()
        if pedido.items > 10:
            # La excepción se lanza dentro del `paso`, así que ese paso queda
            # marcado como ERROR y se ve exactamente dónde se cortó.
            raise HTTPException(status_code=409, detail="Stock insuficiente")

    with paso("Reservando inventario"):
        await _trabajo()

    with paso("Calculando impuestos"):
        await _trabajo(0.005, 0.02)

    return {"pedido": random.randint(1000, 9999), "items": pedido.items}


@app.get("/clientes/{cliente_id}")
async def obtener_cliente(cliente_id: int):
    with paso(f"Buscando cliente {cliente_id} en caché"):
        await _trabajo(0.001, 0.005)

    with paso("Cache miss, consultando base de datos"):
        await _trabajo(0.02, 0.1)

    if cliente_id > 9000:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")

    return {"id": cliente_id, "nombre": "Cliente de prueba"}


@app.post("/pagos")
async def cobrar(pago: PagoIn):
    with paso("Validando datos de la tarjeta"):
        await _trabajo()

    with paso("Solicitando autorización al emisor"):
        await _trabajo(0.05, 0.25)
        # Uno de cada cinco pagos se cae: da material para el visor.
        if random.random() < 0.2:
            raise RuntimeError("El emisor rechazó la operación")

    with paso("Emitiendo comprobante"):
        await _trabajo()

    return {"autorizacion": random.randint(100000, 999999), "monto": pago.monto}


@app.get("/inventario")
async def inventario():
    # Operación sin pasos: el log igual sale, con la entrada y la respuesta.
    await _trabajo()
    return {"articulos": random.randint(50, 500)}


@app.get("/logmon-stats")
async def stats():
    """Cuántos logs se enviaron. Sirve para verificar sin abrir LogMon."""

    return logmon.stats
