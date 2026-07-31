# logmon-client

Instrumentación para apps ASGI que quieran mandar sus operaciones a
[LogMon](https://github.com/fedepuchi/Logsystem-Multidatabase).

Cada request de tu app se convierte en una operación en LogMon, con sus pasos y
el tiempo real de cada uno.

---

## Por qué "operaciones" y no "líneas de log"

El modelo de LogMon no es el de un log plano. Un registro tiene `entrada`,
`resultado`, `metodo` y una **cadena de pasos** con duraciones, y de ahí LogMon
deriva el `estado` y el `tiempo_ms`. Eso encaja con el ciclo de vida de un
request y no encaja con un `logger.info("algo pasó")`, que no tiene ni entrada
ni resultado ni pasos.

Por eso esta librería instrumenta operaciones. Un `logging.Handler` genérico
existiría a costa de un mapeo pobre: sin pasos reales, entrada y resultado
repetidos y `tiempo_ms` siempre en 0.

---

## Uso

```bash
pip install -e .
```

Son tres líneas sobre una app que ya tenés:

```python
from fastapi import FastAPI
from logmon_client import LogMon, paso

app = FastAPI()
logmon = LogMon(base_url="http://localhost:8000", fuente="ventas")
logmon.instrumentar(app)
```

Con eso ya sale un log por request. Los `paso(...)` son opcionales y son lo que
convierte el log en algo que se puede leer:

```python
@app.post("/pedidos")
async def crear_pedido(pedido: PedidoIn):
    with paso("Validando token de sesión"):
        ...
    with paso("Verificando stock"):
        if sin_stock:
            raise HTTPException(409, "Stock insuficiente")
    with paso("Reservando inventario"):
        ...
    return {"ok": True}
```

En LogMon eso queda así:

```
ENTRADA  POST /pedidos                                0ms
SALIDA   Validando token de sesión                   48ms
SALIDA   Verificando stock de 2 artículos            13ms
SALIDA   Reservando inventario                       15ms
SALIDA   Calculando impuestos                        19ms
SALIDA   HTTP 200 POST /pedidos                       5ms
                                    estado: OK   tiempo_ms: 100
```

Y si algo falla, el paso `ERROR` marca exactamente dónde se cortó:

```
ENTRADA  POST /pagos                                              0ms
SALIDA   Validando datos de la tarjeta                           37ms
ERROR    Solicitando autorización al emisor: RuntimeError: ...   61ms
SALIDA   HTTP 500 POST /pagos                                     1ms
                                    estado: ERROR   tiempo_ms: 99
```

El último paso registra la respuesta HTTP que la app efectivamente devolvió,
aunque la operación haya fallado antes. `estado` sigue siendo ERROR: LogMon lo
deriva de que exista **algún** paso ERROR.

`paso()` fuera de un request no hace nada, así que el mismo servicio corre igual
en un script o en un test sin tocar nada.

---

## Se configura por nombre, no por id

La fuente se indica por su nombre (`fuente="ventas"`), no por el `source_id` que
genera la base. El cliente lo resuelve contra `GET /api/sources` en el primer
envío y lo cachea. Si la fuente no existe, avisa **una vez** en el log de la app
y descarta: no queremos que instrumentar llene la salida de errores repetidos.

---

## Garantías

La regla de diseño es una sola: **instrumentar no puede tumbar ni frenar la
app**.

- El envío es asíncrono. El request responde sin esperar a LogMon.
- La cola es acotada (1000 por defecto). Si se llena, se descarta y se cuenta.
  Preferimos perder logs a quedarnos sin memoria por un LogMon caído.
- Ninguna excepción del cliente escapa hacia el código de negocio.
- Se reintenta 2 veces ante fallos de red; los 4xx no se reintentan, porque el
  payload no va a mejorar solo.
- Se recupera solo cuando LogMon vuelve, sin reiniciar la app.

Verificado matando LogMon con la app en marcha: los requests siguieron
devolviendo 200 en 24–79 ms (su latencia normal), el cliente contó los fallos, y
al volver LogMon los envíos se reanudaron sin tocar la app.

**Lo que sí se pierde:** los logs generados mientras LogMon estaba caído. Tras
agotar los reintentos se descartan; no hay buffer en disco ni reenvío posterior.

`logmon.stats` devuelve los contadores por si querés exponerlos:

```python
@app.get("/logmon-stats")
async def stats():
    return logmon.stats
```

---

## El ejemplo

```bash
make install
make ejemplo
```

Levanta una tienda en `http://localhost:9000` con cuatro operaciones ya
instrumentadas — pedidos, clientes, pagos e inventario — que fallan de vez en
cuando a propósito para dar material al visor. Necesita una fuente llamada
`ventas` en LogMon con un motor asignado.

```bash
curl -X POST localhost:9000/pedidos -H 'Content-Type: application/json' -d '{"cliente":42,"items":3}'
```

---

## Tests

```bash
make test
```

23 casos: la construcción del payload contra el contrato de `LogCreate`, el
aislamiento de pasos entre requests concurrentes (que es lo que justifica usar
`ContextVar` y no una global), y el middleware contra una app FastAPI real.

---

## Seguridad

LogMon **no tiene autenticación**. La misma API que recibe logs permite leerlos
todos, crear y borrar conexiones y cambiar el motor de una fuente. Mientras siga
así, no debe exponerse más allá de la máquina local.

En `docker-compose.yml` el backend publica `"8000:8000"`, que escucha en todas
las interfaces. Para atarlo a localhost:

```yaml
ports:
  - "127.0.0.1:8000:8000"
```

---

## Alcance

- Sólo ASGI (FastAPI, Starlette, Litestar). Flask/Django WSGI no están cubiertos.
- Un POST por operación: LogMon no tiene endpoint de lote todavía.
- Probado contra un stub que valida con el `LogCreate` real de LogMon, no contra
  una instancia con los cinco motores levantados.
