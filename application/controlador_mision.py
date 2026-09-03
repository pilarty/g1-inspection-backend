from typing import Optional

from infrastructure import repositorio_datos
from models.schemas import MissionIn, MissionStatusIn


def definir_mision(m: MissionIn) -> dict:
    """Reemplaza la misión activa (lista de waypoints a recorrer)."""
    mision = m.model_dump()
    repositorio_datos.guardar_mision(mision)
    return mision


def obtener_mision() -> Optional[dict]:
    """Devuelve None si todavía no se definió ninguna misión."""
    return repositorio_datos.obtener_mision()


def reportar_estado(s: MissionStatusIn) -> None:
    """Telemetría de baja frecuencia: pose y progreso del robot en la misión."""
    repositorio_datos.guardar_estado_mision(s.model_dump())


def obtener_estado_mision() -> Optional[dict]:
    return repositorio_datos.obtener_estado_mision()
