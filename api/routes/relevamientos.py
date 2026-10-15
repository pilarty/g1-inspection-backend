from fastapi import APIRouter

from application import controlador_relevamiento
from infrastructure import trayectoria
from models.schemas import PoseIn, RoomLayoutIn

router = APIRouter()


@router.post("/room")
def guardar_room_layout(room: RoomLayoutIn):
    controlador_relevamiento.registrar_room_layout(room)
    # Si ya hay una inspección andando, el plano queda guardado con ella
    from infrastructure import nube
    if nube.relevamiento_actual is not None:
        trayectoria.subir_plano(nube.relevamiento_actual, room.model_dump())
    return {"ok": True}


@router.get("/room")
def obtener_room_layout():
    return controlador_relevamiento.obtener_room_layout()


@router.post("/pose")
def registrar_pose(p: PoseIn):
    """Posición del robot (la manda el simulador o el robot cada medio segundo)."""
    trayectoria.registrar(p.x, p.y, p.yaw, p.timestamp)
    return {"ok": True}


@router.get("/pose")
def obtener_pose():
    """Última posición conocida (para mostrar al robot en vivo). None si todavía no llegó ninguna."""
    return trayectoria.ultima
