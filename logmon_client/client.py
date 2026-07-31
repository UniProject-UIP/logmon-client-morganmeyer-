"""Transporte hacia LogMon.

La regla que manda acá: **instrumentar no puede tumbar ni frenar la app**. Si
LogMon está caído, lento o mal configurado, la app instrumentada tiene que
seguir respondiendo igual de rápido. Por eso el envío es asíncrono, la cola es
acotada y ninguna excepción de este módulo escapa hacia el código de negocio:
se cuenta y se sigue.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger("logmon_client")


@dataclass
class Contadores:
    encolados: int = 0
    enviados: int = 0
    fallidos: int = 0
    descartados: int = 0
    ultimo_error: Optional[str] = None

    def como_dict(self) -> Dict[str, Any]:
        return {
            "encolados": self.encolados,
            "enviados": self.enviados,
            "fallidos": self.fallidos,
            "descartados": self.descartados,
            "ultimo_error": self.ultimo_error,
        }


class FuenteDesconocida(Exception):
    """La fuente configurada no existe en LogMon."""


class LogMon:
    """Cliente de ingesta.

    :param base_url: dónde escucha LogMon.
    :param fuente: nombre de la fuente, tal como figura en LogMon. Se resuelve
        a su ``source_id`` en el primer envío; se usa el nombre y no el id
        porque el id lo genera la base y no es algo que quieras hardcodear en
        la configuración de cada app.
    :param cola_max: cuántos logs pendientes se aguantan antes de empezar a
        descartar. Acotado a propósito: preferimos perder logs a quedarnos sin
        memoria por un LogMon caído.
    """

    def __init__(
        self,
        base_url: str = "http://localhost:8000",
        fuente: str = "",
        parent_type: str = "API",
        cola_max: int = 1000,
        workers: int = 2,
        timeout: float = 3.0,
        reintentos: int = 2,
    ) -> None:
        if not fuente:
            raise ValueError("Hay que indicar el nombre de la fuente")

        self.base_url = base_url.rstrip("/")
        self.fuente = fuente
        self.parent_type = parent_type
        self.cola_max = cola_max
        self.workers_n = workers
        self.timeout = timeout
        self.reintentos = reintentos

        self.contadores = Contadores()

        self._cola: Optional[asyncio.Queue] = None
        self._tareas: List[asyncio.Task] = []
        self._http: Optional[httpx.AsyncClient] = None
        self._source_id: Optional[str] = None
        self._lock_resolucion: Optional[asyncio.Lock] = None
        self._aviso_fuente_dado = False

    # -- arranque perezoso -------------------------------------------------

    def _arrancar_si_hace_falta(self) -> None:
        """Crea cola, cliente y workers la primera vez, ya dentro del loop.

        No se hace en __init__ porque en Python 3.9 tanto ``asyncio.Queue``
        como ``asyncio.Lock`` se atan al loop vigente al construirse, y el
        cliente suele instanciarse a nivel de módulo, antes de que exista uno.
        """

        if self._cola is not None:
            return

        self._cola = asyncio.Queue(maxsize=self.cola_max)
        self._lock_resolucion = asyncio.Lock()
        self._http = httpx.AsyncClient(timeout=self.timeout)
        self._tareas = [asyncio.create_task(self._worker()) for _ in range(self.workers_n)]

    # -- entrada -----------------------------------------------------------

    def registrar(self, payload: Dict[str, Any]) -> None:
        """Encola un log. No bloquea y no lanza nunca."""

        try:
            self._arrancar_si_hace_falta()
            self._cola.put_nowait(payload)  # type: ignore[union-attr]
            self.contadores.encolados += 1
        except asyncio.QueueFull:
            self.contadores.descartados += 1
        except RuntimeError:
            # Sin event loop corriendo: la app no es ASGI o estamos fuera del
            # ciclo de vida normal. Se descarta en silencio.
            self.contadores.descartados += 1
        except Exception as exc:  # pragma: no cover - red de seguridad
            self.contadores.descartados += 1
            self.contadores.ultimo_error = f"{type(exc).__name__}: {exc}"

    # -- salida ------------------------------------------------------------

    async def _resolver_fuente(self) -> Optional[str]:
        """Traduce el nombre de la fuente a su source_id. Cachea el resultado."""

        if self._source_id is not None:
            return self._source_id

        async with self._lock_resolucion:  # type: ignore[union-attr]
            if self._source_id is not None:
                return self._source_id

            resp = await self._http.get(f"{self.base_url}/api/sources")  # type: ignore[union-attr]
            resp.raise_for_status()

            for fuente in resp.json():
                if fuente.get("name") == self.fuente:
                    self._source_id = str(fuente["id"])
                    return self._source_id

            raise FuenteDesconocida(
                f"La fuente '{self.fuente}' no existe en {self.base_url}. "
                "Creala en LogMon y asignale un motor."
            )

    async def _worker(self) -> None:
        while True:
            payload = await self._cola.get()  # type: ignore[union-attr]
            try:
                await self._enviar(payload)
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # pragma: no cover - red de seguridad
                self.contadores.fallidos += 1
                self.contadores.ultimo_error = f"{type(exc).__name__}: {exc}"
            finally:
                self._cola.task_done()  # type: ignore[union-attr]

    async def _enviar(self, payload: Dict[str, Any]) -> None:
        try:
            source_id = await self._resolver_fuente()
        except FuenteDesconocida as exc:
            self.contadores.fallidos += 1
            self.contadores.ultimo_error = str(exc)
            if not self._aviso_fuente_dado:
                # Una sola vez: si no, cada request ensucia los logs de la app.
                logger.warning("%s", exc)
                self._aviso_fuente_dado = True
            return
        except httpx.HTTPError as exc:
            self.contadores.fallidos += 1
            self.contadores.ultimo_error = f"No se pudo listar fuentes: {exc}"
            return

        payload = {**payload, "source_id": source_id}
        url = f"{self.base_url}/api/logs"

        for intento in range(self.reintentos + 1):
            try:
                resp = await self._http.post(url, json=payload)  # type: ignore[union-attr]
            except httpx.HTTPError as exc:
                if intento == self.reintentos:
                    self.contadores.fallidos += 1
                    self.contadores.ultimo_error = f"{type(exc).__name__}: {exc}"
                    return
                await asyncio.sleep(0.2 * (intento + 1))
                continue

            if resp.status_code == 201:
                self.contadores.enviados += 1
                return

            # 4xx no se reintenta: el payload no va a mejorar solo.
            if 400 <= resp.status_code < 500:
                self.contadores.fallidos += 1
                self.contadores.ultimo_error = f"HTTP {resp.status_code}: {resp.text[:200]}"
                return

            if intento == self.reintentos:
                self.contadores.fallidos += 1
                self.contadores.ultimo_error = f"HTTP {resp.status_code}"
                return
            await asyncio.sleep(0.2 * (intento + 1))

    # -- cierre ------------------------------------------------------------

    async def cerrar(self, espera: float = 3.0) -> None:
        """Vacía lo pendiente y cierra. Se llama en el shutdown de la app."""

        if self._cola is None:
            return

        try:
            await asyncio.wait_for(self._cola.join(), timeout=espera)
        except asyncio.TimeoutError:
            logger.warning(
                "Quedaron %d logs sin enviar al cerrar", self._cola.qsize()
            )

        for tarea in self._tareas:
            tarea.cancel()
        await asyncio.gather(*self._tareas, return_exceptions=True)
        self._tareas = []

        if self._http is not None:
            await self._http.aclose()
            self._http = None
        self._cola = None

    # -- diagnóstico -------------------------------------------------------

    @property
    def stats(self) -> Dict[str, Any]:
        pendientes = self._cola.qsize() if self._cola is not None else 0
        return {**self.contadores.como_dict(), "pendientes": pendientes}
