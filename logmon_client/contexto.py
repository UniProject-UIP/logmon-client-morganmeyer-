"""La operación en curso y sus pasos.

Cada request de la app instrumentada es una *operación*. Mientras se procesa,
el código de negocio puede ir anotando pasos con ``paso(...)``; al terminar, el
middleware los convierte en el ``steps`` que espera LogMon.

Se usa un ContextVar en vez de una variable global porque bajo asyncio hay
muchos requests en vuelo a la vez y cada uno tiene que ver sólo sus pasos.
"""

from __future__ import annotations

import time
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Iterator, List, Optional

# Tipos de paso que acepta LogMon. ENTRADA lo pone el middleware al abrir la
# operación; el código de la app sólo genera SALIDA o ERROR.
SALIDA = "SALIDA"
ERROR = "ERROR"


@dataclass
class Paso:
    descripcion: str
    tipo: str
    duration_ms: int


@dataclass
class Operacion:
    """Una unidad de trabajo: típicamente un request HTTP."""

    metodo: str
    entrada: str
    inicio: float
    pasos: List[Paso] = field(default_factory=list)

    def anotar(self, descripcion: str, tipo: str, duration_ms: int) -> None:
        self.pasos.append(Paso(descripcion=descripcion, tipo=tipo, duration_ms=duration_ms))

    @property
    def tiene_error(self) -> bool:
        return any(p.tipo == ERROR for p in self.pasos)


_actual: ContextVar[Optional[Operacion]] = ContextVar("logmon_operacion", default=None)


def abrir(metodo: str, entrada: str) -> Operacion:
    op = Operacion(metodo=metodo, entrada=entrada, inicio=time.perf_counter())
    _actual.set(op)
    return op


def actual() -> Optional[Operacion]:
    return _actual.get()


def cerrar() -> None:
    _actual.set(None)


@contextmanager
def paso(descripcion: str) -> Iterator[None]:
    """Anota un paso de la operación en curso, midiendo cuánto tardó.

        with paso("Verificando stock"):
            ...

    Si el bloque lanza una excepción, el paso queda marcado como ERROR y la
    excepción se vuelve a lanzar: el paso describe qué se estaba haciendo
    cuando falló.

    Fuera de una operación (por ejemplo en un script suelto o en un test) no
    hace nada. Instrumentar no debería obligar a cambiar cómo se ejecuta el
    código.
    """

    op = _actual.get()
    if op is None:
        yield
        return

    arranque = time.perf_counter()
    try:
        yield
    except Exception as exc:
        transcurrido = int((time.perf_counter() - arranque) * 1000)
        op.anotar(f"{descripcion}: {type(exc).__name__}: {exc}", ERROR, transcurrido)
        raise
    else:
        transcurrido = int((time.perf_counter() - arranque) * 1000)
        op.anotar(descripcion, SALIDA, transcurrido)


def anotar(descripcion: str) -> None:
    """Anota un paso instantáneo, sin bloque ni duración medible."""

    op = _actual.get()
    if op is not None:
        op.anotar(descripcion, SALIDA, 0)
