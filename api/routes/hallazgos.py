from fastapi import APIRouter

from application import controlador_relevamiento
from models.schemas import DeteccionIn

router = APIRouter()


@router.post("/detections")
def crear_deteccion(det: DeteccionIn):
    registro = controlador_relevamiento.registrar_deteccion(det)
    return {"ok": True, "id": registro["id"]}


@router.get("/detections")
def listar_detecciones():
    return controlador_relevamiento.obtener_detecciones()
