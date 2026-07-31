"""Middleware ASGI: un request de la app = una operación en LogMon.

Es ASGI puro a propósito, sin depender de Starlette, para que la única
dependencia en tiempo de ejecución siga siendo httpx y sirva con cualquier
framework ASGI.
"""

from __future__ import annotations

import time
from typing import Any, Callable, Dict, Iterable, Optional

from logmon_client import contexto
from logmon_client.payload import construir

# Rutas que no vale la pena registrar: ensucian el visor y no son operaciones
# de negocio.
EXCLUIDAS_POR_DEFECTO = ("/health", "/docs", "/openapi.json", "/redoc", "/favicon.ico")


class LogMonMiddleware:
    def __init__(
        self,
        app: Callable,
        cliente: Any,
        excluir: Optional[Iterable[str]] = None,
    ) -> None:
        self.app = app
        self.cliente = cliente
        self.excluir = tuple(excluir) if excluir is not None else EXCLUIDAS_POR_DEFECTO

    async def __call__(self, scope: Dict[str, Any], receive: Callable, send: Callable) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        ruta = scope.get("path", "")
        if ruta.startswith(self.excluir):
            await self.app(scope, receive, send)
            return

        metodo = scope.get("method", "GET")
        query = scope.get("query_string", b"").decode("latin-1")
        entrada = f"{metodo} {ruta}" + (f"?{query}" if query else "")

        op = contexto.abrir(metodo, entrada)
        arranque = time.perf_counter()
        estado_http = {"codigo": 500}

        async def send_espiado(message: Dict[str, Any]) -> None:
            if message.get("type") == "http.response.start":
                estado_http["codigo"] = message.get("status", 500)
            await send(message)

        try:
            await self.app(scope, receive, send_espiado)
        except Exception as exc:
            self._registrar(
                op,
                arranque,
                resultado=f"HTTP 500 {entrada}",
                fallo=f"{type(exc).__name__}: {exc}",
            )
            raise
        else:
            codigo = estado_http["codigo"]
            resultado = f"HTTP {codigo} {entrada}"
            # Un 5xx sin excepción (por ejemplo un JSONResponse(status_code=500))
            # tambien es un fallo desde el punto de vista del negocio.
            fallo = resultado if codigo >= 500 else None
            self._registrar(op, arranque, resultado=resultado, fallo=fallo)
        finally:
            contexto.cerrar()

    def _registrar(
        self,
        op: contexto.Operacion,
        arranque: float,
        resultado: str,
        fallo: Optional[str] = None,
    ) -> None:
        total_ms = int((time.perf_counter() - arranque) * 1000)
        payload = construir(
            op,
            parent_type=self.cliente.parent_type,
            total_ms=total_ms,
            resultado=resultado,
            fallo=fallo,
        )
        self.cliente.registrar(payload)
