"""Cliente de instrumentación para LogMon.

Uso mínimo con FastAPI:

    from fastapi import FastAPI
    from logmon_client import LogMon, paso

    app = FastAPI()
    logmon = LogMon(base_url="http://localhost:8000", fuente="ventas")
    logmon.instrumentar(app)

    @app.post("/pedidos")
    async def crear_pedido():
        with paso("Verificando stock"):
            ...
        with paso("Reservando inventario"):
            ...
        return {"ok": True}

Cada request queda como una operación en LogMon, con sus pasos y el tiempo real
de cada uno. Si LogMon está caído, la app no se entera.
"""

from logmon_client.client import Contadores, FuenteDesconocida, LogMon as _LogMonBase
from logmon_client.contexto import anotar, paso
from logmon_client.middleware import LogMonMiddleware

__all__ = [
    "LogMon",
    "LogMonMiddleware",
    "Contadores",
    "FuenteDesconocida",
    "paso",
    "anotar",
]


class LogMon(_LogMonBase):
    """Cliente con el atajo de instrumentación para apps ASGI."""

    def instrumentar(self, app, excluir=None) -> None:
        """Engancha el middleware y el cierre ordenado a una app ASGI.

        Funciona con cualquier app estilo Starlette/FastAPI. Si el objeto no
        expone ``add_middleware`` se lanza TypeError: es un error de uso y es
        mejor que salte al arrancar y no en silencio con cada request.
        """

        if not hasattr(app, "add_middleware"):
            raise TypeError(
                "instrumentar() espera una app ASGI estilo Starlette/FastAPI. "
                "Para otras, envolvé a mano: app = LogMonMiddleware(app, cliente)"
            )

        app.add_middleware(LogMonMiddleware, cliente=self, excluir=excluir)

        # El shutdown importa: sin esto los logs encolados al final del proceso
        # se pierden al morir el loop.
        try:
            app.add_event_handler("shutdown", self.cerrar)
        except AttributeError:  # pragma: no cover - apps ASGI mínimas
            pass
