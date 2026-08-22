from typing import List, Optional

from domain.seguimiento_detecciones import armar_registro
from infrastructure import repositorio_datos, storage_s3
from models.schemas import DeteccionIn, RoomLayoutIn


def registrar_deteccion(det: DeteccionIn) -> dict:
    ruta_imagen = storage_s3.guardar_imagen(det.imagen_base64)
    registro = armar_registro(det, ruta_imagen)
    repositorio_datos.agregar_deteccion(registro)
    return registro


def obtener_detecciones() -> List[dict]:
    return repositorio_datos.listar_detecciones()


def registrar_room_layout(room: RoomLayoutIn) -> None:
    """Lo llama extraer_dimensiones.py una vez, al arrancar (no por cada frame)."""
    repositorio_datos.guardar_room_layout(room.model_dump())


def obtener_room_layout() -> Optional[dict]:
    """Devuelve None si extraer_dimensiones.py todavía no corrió."""
    return repositorio_datos.obtener_room_layout()


def estado_sistema() -> dict:
    return {
        "status": "ok",
        "detecciones_guardadas": len(repositorio_datos.listar_detecciones()),
        "room_cargado": repositorio_datos.obtener_room_layout() is not None,
    }
