from fastapi import APIRouter

from application import controlador_mision
from models.schemas import MissionIn, MissionStatusIn

router = APIRouter()


@router.post("/mission")
def definir_mision(m: MissionIn):
    mision = controlador_mision.definir_mision(m)
    return {"ok": True, "mission": mision}


@router.get("/mission")
def obtener_mision():
    return controlador_mision.obtener_mision()


@router.post("/mission/status")
def reportar_estado_mision(s: MissionStatusIn):
    controlador_mision.reportar_estado(s)
    return {"ok": True}


@router.get("/mission/status")
def obtener_estado_mision():
    return controlador_mision.obtener_estado_mision()
