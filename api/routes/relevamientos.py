from fastapi import APIRouter

from application import controlador_relevamiento
from models.schemas import RoomLayoutIn

router = APIRouter()


@router.post("/room")
def guardar_room_layout(room: RoomLayoutIn):
    controlador_relevamiento.registrar_room_layout(room)
    return {"ok": True}


@router.get("/room")
def obtener_room_layout():
    return controlador_relevamiento.obtener_room_layout()
