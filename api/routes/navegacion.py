import time

from fastapi import APIRouter, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response

from api import codec_navegacion
from application import controlador_navegacion

router = APIRouter(prefix="/navegacion")


def _atender(nombre: str, cuerpo: bytes) -> bytes:
    try:
        args = codec_navegacion.desempaquetar(cuerpo)
    except Exception:
        raise HTTPException(400, "cuerpo invalido")
    if not isinstance(args, (list, tuple)):
        raise HTTPException(400, "cuerpo invalido")
    t0 = time.perf_counter()
    try:
        r = controlador_navegacion.calcular(nombre, tuple(args))
    except KeyError:
        raise HTTPException(404, f"calculo desconocido: {nombre}")
    except TypeError as e:  # argumentos que no corresponden al calculo
        raise HTTPException(422, f"argumentos invalidos: {e}")
    return codec_navegacion.empaquetar({"r": r, "ms": 1000 * (time.perf_counter() - t0)})


@router.post("/{nombre}")
async def calcular(nombre: str, request: Request):
    """Calculos de navegacion que el robot delega (planificar, explorar, decidir inspeccion...). El robot espera la respuesta."""
    cuerpo = await request.body()
    return Response(await run_in_threadpool(_atender, nombre, cuerpo), media_type="application/octet-stream")
