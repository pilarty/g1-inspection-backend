from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from infrastructure import nube

router = APIRouter(prefix="/nube")


class LoginIn(BaseModel):
    usuario: str
    clave: str


class RelevamientoIn(BaseModel):
    relevamiento_id: int


@router.post("/login")
def login(d: LoginIn):
    try:
        nube.iniciar_sesion(d.usuario, d.clave)
    except Exception:
        raise HTTPException(401, "no se pudo iniciar sesion")
    return {"ok": True}


@router.post("/relevamiento")
def elegir_relevamiento(d: RelevamientoIn):
    nube.relevamiento_actual = d.relevamiento_id
    return {"ok": True}


@router.get("/estado")
def estado():
    return {"sesion": nube.sesion_activa(),
            "relevamiento_id": nube.relevamiento_actual}
