from typing import List, Optional

detecciones: List[dict] = []
room_layout: Optional[dict] = None

def agregar_deteccion(registro: dict) -> None:
    detecciones.append(registro)


def listar_detecciones() -> List[dict]:
    return detecciones


def guardar_room_layout(room: dict) -> None:
    global room_layout
    room_layout = room


def obtener_room_layout() -> Optional[dict]:
    return room_layout
