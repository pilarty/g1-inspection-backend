from typing import List, Optional

# Guardado en memoria: alcanza para la demo. Se pierde al reiniciar el proceso.
# Cuando pasen a la versión "en serio", esto se reemplaza por Postgres
# (tabla `hallazgo`, tal como está en el modelo de datos del TFI).
_detecciones: List[dict] = []
_room_layout: Optional[dict] = None


def agregar_deteccion(registro: dict) -> None:
    _detecciones.append(registro)


def listar_detecciones() -> List[dict]:
    return _detecciones


def guardar_room_layout(room: dict) -> None:
    global _room_layout
    _room_layout = room


def obtener_room_layout() -> Optional[dict]:
    return _room_layout
