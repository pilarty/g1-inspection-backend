from fastapi import APIRouter

from application import controlador_relevamiento

router = APIRouter()


@router.get("/health")
def health():
    return controlador_relevamiento.estado_sistema()
