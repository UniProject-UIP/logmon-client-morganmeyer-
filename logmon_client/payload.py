"""Traducción de una operación al formato que espera LogMon.

LogMon no acepta ``estado`` ni ``tiempo_ms`` del cliente: los deriva de los
pasos. ``estado`` es ERROR si algún paso lo es, y ``tiempo_ms`` es la suma de
los ``duration_ms``. Así que para que el tiempo que ve LogMon coincida con lo
que realmente tardó el request, el paso final absorbe el tiempo que no quedó
atribuido a ningún paso intermedio.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from logmon_client.contexto import ERROR, SALIDA, Operacion

ENTRADA = "ENTRADA"


def construir(
    op: Operacion,
    parent_type: str,
    total_ms: int,
    resultado: str,
    fallo: Optional[str] = None,
) -> Dict[str, Any]:
    """Arma el cuerpo de ``POST /api/logs``.

    ``source_id`` no se pone acá: lo completa el cliente cuando resuelve el
    nombre de la fuente contra LogMon.
    """

    steps = [
        {"orden": 1, "tipo": ENTRADA, "contenido": op.entrada, "duration_ms": 0}
    ]

    for paso in op.pasos:
        steps.append(
            {
                "orden": len(steps) + 1,
                "tipo": paso.tipo,
                "contenido": paso.descripcion,
                "duration_ms": paso.duration_ms,
            }
        )

    # El sobrante es el tiempo del request que no cayó dentro de ningún paso:
    # framework, serialización, lo que no se instrumentó.
    atribuido = sum(p.duration_ms for p in op.pasos)
    sobrante = max(0, total_ms - atribuido)

    if fallo is not None and not op.tiene_error:
        # La operación se cayó fuera de un `paso(...)`: lo registramos igual,
        # porque si no LogMon lo daría por OK.
        steps.append(
            {"orden": len(steps) + 1, "tipo": ERROR, "contenido": fallo, "duration_ms": sobrante}
        )
    else:
        steps.append(
            {"orden": len(steps) + 1, "tipo": SALIDA, "contenido": resultado, "duration_ms": sobrante}
        )

    return {
        "parent_type": parent_type,
        "entrada": op.entrada,
        "resultado": fallo or resultado,
        "metodo": op.metodo,
        "fecha": datetime.now(timezone.utc).isoformat(),
        "steps": steps,
    }
