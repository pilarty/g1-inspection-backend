import json
from typing import Optional

import requests
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from infrastructure import nube
from infrastructure.robot import conexion
from infrastructure.robot.conexion import Conexion

router = APIRouter(prefix="/robot")

# Robot con el que la app quedo conectada (perfil completo, con contraseñas: nunca se devuelve)
robot_activo: Optional[dict] = None
movimiento_autorizado = False


class ConexionIn(BaseModel):
    host: str
    interfaz: Optional[str] = None
    ssh_usuario: str
    ssh_password: str = ""
    ssh_puerto: int = Field(22, ge=1, le=65535)
    dds_domain_id: int = Field(0, ge=0, le=232)
    robot_id: Optional[int] = None  # al editar: la contraseña vacia se toma del perfil guardado


def _a_conexion(d: ConexionIn) -> Conexion:
    return Conexion(
        host=d.host.strip(), ssh_usuario=d.ssh_usuario, ssh_password=d.ssh_password, ssh_puerto=d.ssh_puerto,
        dds_domain_id=d.dds_domain_id, interfaz=d.interfaz or None,
    )


def _ndjson(eventos):
    for e in eventos:
        yield json.dumps(e, ensure_ascii=False) + "\n"


@router.get("/interfaces")
def interfaces(host: str = ""):
    lista = conexion.listar_interfaces()
    sugerida = conexion.sugerir_interfaz(host.strip(), lista)
    return {"interfaces": lista, "sugerida": sugerida["nombre"] if sugerida else None}


def _completar_credenciales(d: ConexionIn) -> ConexionIn:
    if d.robot_id is None or d.ssh_password:
        return d
    guardadas = _credenciales_nube(d.robot_id)
    return d.model_copy(update={"ssh_password": guardadas.get("ssh_password", "")})


@router.post("/prueba")
def probar(d: ConexionIn):
    """Prueba todos los canales; emite una linea JSON por evento para mostrar el avance en vivo."""
    cfg = _a_conexion(_completar_credenciales(d))
    return StreamingResponse(_ndjson(conexion.probar(cfg)), media_type="application/x-ndjson")


# ─── Reconexion con un perfil guardado en la nube ─────────────────────────────

def _leer_nube(ruta: str) -> dict:
    if not nube.sesion_activa():
        raise HTTPException(401, "sin sesion")
    try:
        r = nube.reenviar("GET", ruta)
        if r.status_code == 404:
            raise HTTPException(404, "robot no encontrado")
        r.raise_for_status()
        return r.json()
    except requests.RequestException:
        raise HTTPException(502, "no se pudo leer el perfil del robot en la nube")


def _credenciales_nube(robot_id: int) -> dict:
    return _leer_nube(f"robots/{robot_id}/credenciales") or {}


def _perfil_nube(robot_id: int) -> dict:
    robot = _leer_nube(f"robots/{robot_id}")
    if not robot.get("conexion"):
        raise HTTPException(409, "el robot no tiene un perfil de conexion guardado")
    return {**robot, "credenciales": _credenciales_nube(robot_id)}


def _desde_perfil(perfil: dict) -> Conexion:
    c, s = perfil["conexion"], perfil["credenciales"] or {}
    return Conexion(
        host=c["host"], ssh_usuario=c["ssh_usuario"], ssh_password=s.get("ssh_password", ""),
        ssh_puerto=int(c.get("ssh_puerto") or 22), dds_domain_id=int(c.get("dds_domain_id") or 0),
        interfaz=None,  # se vuelve a detectar en cada conexion, no se confia en la guardada
    )


def _guardar_prueba(robot_id: int, fin: dict, pasos: list, interfaz) -> None:
    try:
        nube.reenviar("PUT", f"robots/{robot_id}/prueba", cuerpo={
            "ultima_prueba_fecha": fin["fecha"],
            "ultima_prueba": {"resultado": fin["resultado"], "tipo": "rapida", "interfaz": interfaz, "pasos": pasos},
        })
    except requests.RequestException:
        pass  # no impide usar el robot


@router.post("/reconectar/{robot_id}")
def reconectar(robot_id: int):
    """Comprobacion rapida (red, SSH, DDS) con el perfil guardado. Nunca envia ordenes de movimiento."""
    global robot_activo, movimiento_autorizado
    perfil = _perfil_nube(robot_id)
    cfg = _desde_perfil(perfil)
    robot_activo, movimiento_autorizado = None, False

    def eventos():
        global robot_activo
        pasos, interfaz = [], None
        for e in conexion.probar(cfg, conexion.PASOS_RAPIDOS):
            if e["tipo"] == "inicio":
                interfaz = e["interfaz"]
            elif e["tipo"] == "paso" and e["estado"] != "en_curso":
                pasos.append({k: e.get(k) for k in ("paso", "estado", "mensaje", "ms")})
            elif e["tipo"] == "fin":
                _guardar_prueba(robot_id, e, pasos, interfaz)
                if e["resultado"] == "ok":
                    robot_activo = {"id": robot_id, "codigo": perfil.get("codigo"), "conexion": cfg, "interfaz": interfaz}
            yield e

    return StreamingResponse(_ndjson(eventos()), media_type="application/x-ndjson")


@router.get("/activo")
def activo():
    if robot_activo is None:
        return {"conectado": False}
    return {
        "conectado": True, "id": robot_activo["id"], "codigo": robot_activo["codigo"],
        "interfaz": robot_activo["interfaz"], "movimiento_autorizado": movimiento_autorizado,
    }


class AutorizarIn(BaseModel):
    espacio_despejado: bool
    soporte_seguridad: bool
    operador_con_control: bool


@router.post("/movimiento/autorizar")
def autorizar_movimiento(d: AutorizarIn):
    """Confirmacion explicita del operador; sin ella la app no envia ordenes de movimiento."""
    global movimiento_autorizado
    if robot_activo is None:
        raise HTTPException(409, "no hay un robot conectado")
    if not (d.espacio_despejado and d.soporte_seguridad and d.operador_con_control):
        raise HTTPException(422, "faltan confirmaciones de seguridad")
    movimiento_autorizado = True
    return {"ok": True}


@router.post("/parada")
def parada_emergencia():
    """Parada de emergencia: amortigua el robot conectado y retira el permiso de movimiento."""
    global movimiento_autorizado
    movimiento_autorizado = False  # aunque falle el envio: hay que volver a confirmar para moverlo
    if robot_activo is None:
        raise HTTPException(409, "no hay un robot conectado")
    return conexion.parar_emergencia(robot_activo["conexion"])


@router.post("/desconectar")
def desconectar():
    global robot_activo, movimiento_autorizado
    robot_activo, movimiento_autorizado = None, False
    return {"ok": True}
