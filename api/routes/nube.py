from datetime import datetime, timezone
from typing import Optional

import requests
from fastapi import APIRouter, Body, HTTPException, Request, Response
from pydantic import BaseModel

from infrastructure import nube, repositorio_datos, trayectoria

router = APIRouter(prefix="/nube")

# Solo se reenvian estos recursos de la API de AWS
RECURSOS = {
    "proyectos", "edificaciones", "robots", "usuarios", "documentos",
    "relevamientos", "hallazgos", "informes", "archivos", "resumen", "yo", "plantas",
}


class LoginIn(BaseModel):
    usuario: str
    clave: str


class RelevamientoIn(BaseModel):
    relevamiento_id: int


class IniciarIn(BaseModel):
    edificacion_id: int
    robot_id: int
    fecha_programada: Optional[str] = None
    planta: Optional[str] = None  # piso que se inspecciona (ej. "PB", "Piso 1", "Subsuelo 1")


def _ahora() -> str:
    return datetime.now(timezone.utc).isoformat()


def _finalizar(rid: int) -> None:
    """Marca un relevamiento como finalizado en la nube."""
    r = nube.reenviar("PUT", f"relevamientos/{rid}",
                      cuerpo={"fecha_fin": _ahora(), "estado": "finalizado"})
    r.raise_for_status()


@router.post("/login")
def login(d: LoginIn):
    try:
        nube.iniciar_sesion(d.usuario, d.clave)
    except Exception:
        raise HTTPException(401, "no se pudo iniciar sesion")
    return {"ok": True, "usuario": nube.nombre_usuario}


@router.post("/logout")
def logout():
    nube.cerrar_sesion()
    return {"ok": True}


@router.post("/relevamiento")
def elegir_relevamiento(d: RelevamientoIn):
    nube.relevamiento_actual = d.relevamiento_id
    return {"ok": True}


@router.post("/relevamientos/iniciar")
def iniciar_relevamiento(d: IniciarIn):
    """Crea el relevamiento en la nube; desde aqui cada deteccion se envia a el."""
    if not nube.sesion_activa():
        raise HTTPException(401, "sin sesion")
    try:
        anterior = nube.relevamiento_actual
        if anterior is not None:
            nube.relevamiento_actual = None
            try:
                _finalizar(anterior)
            except requests.RequestException:
                pass  # no impide empezar uno nuevo
        cuerpo = {
            "edificacion_id": d.edificacion_id,
            # (el operador lo define la API de AWS a partir del token)
            "robot_id": d.robot_id,
            "fecha_inicio": _ahora(),
            "estado": "en_curso",
        }
        if d.fecha_programada:
            cuerpo["fecha_programada"] = d.fecha_programada
        r = nube.reenviar("POST", "relevamientos", cuerpo=cuerpo)
        r.raise_for_status()
    except (requests.RequestException, RuntimeError):
        raise HTTPException(502, "no se pudo crear el relevamiento en la nube")
    relevamiento = r.json()
    nube.relevamiento_actual = relevamiento["id"]
    if d.planta:
        try:
            nube.reenviar("PUT", f"relevamientos/{relevamiento['id']}/planta", cuerpo={"planta": d.planta}).raise_for_status()
        except requests.RequestException:
            print("[nube] no se pudo guardar la planta de la inspección")
    # Si el simulador ya mandó el plano antes de empezar, se guarda con esta inspección
    trayectoria.subir_plano(relevamiento["id"], repositorio_datos.obtener_room_layout())
    return relevamiento


@router.post("/relevamientos/detener")
def detener_relevamiento():
    """Deja de enviar detecciones y marca el relevamiento como finalizado."""
    trayectoria.enviar_pendientes()  # que no se pierdan los últimos puntos del camino
    rid = nube.relevamiento_actual
    nube.relevamiento_actual = None
    if rid is not None and nube.sesion_activa():
        try:
            _finalizar(rid)
        except requests.RequestException:
            raise HTTPException(502, "no se pudo cerrar el relevamiento en la nube")
    return {"ok": True}


@router.get("/estado")
def estado():
    return {
        "sesion": nube.sesion_activa(),
        "relevamiento_id": nube.relevamiento_actual,
        "usuario": nube.nombre_usuario,
    }


@router.api_route("/api/{ruta:path}", methods=["GET", "POST", "PUT", "DELETE"])
def reenviar(ruta: str, request: Request, cuerpo: Optional[dict] = Body(default=None)):
    if not nube.sesion_activa():
        raise HTTPException(401, "sin sesion")
    if ruta.split("/")[0] not in RECURSOS:
        raise HTTPException(404, "recurso desconocido")
    if "credenciales" in ruta.split("/"):
        # las contraseñas de los robots solo las lee este backend al reconectar, nunca la interfaz
        raise HTTPException(403, "no permitido")
    try:
        r = nube.reenviar(request.method, ruta, dict(request.query_params), cuerpo)
    except requests.RequestException:
        raise HTTPException(502, "no se pudo conectar con la nube")
    return Response(
        content=r.content,
        status_code=r.status_code,
        media_type=r.headers.get("content-type", "application/json"),
    )
