from typing import List, Optional

detecciones: List[dict] = []
room_layout: Optional[dict] = None
mission: Optional[dict] = None
mission_status: Optional[dict] = None

def agregar_deteccion(registro: dict) -> None:
    detecciones.append(registro)


def listar_detecciones() -> List[dict]:
    return detecciones


def guardar_room_layout(room: dict) -> None:
    global room_layout
    room_layout = room


def obtener_room_layout() -> Optional[dict]:
    return room_layout


def guardar_mision(m: dict) -> None:
    global mission
    mission = m


def obtener_mision() -> Optional[dict]:
    return mission


def guardar_estado_mision(s: dict) -> None:
    global mission_status
    mission_status = s


def obtener_estado_mision() -> Optional[dict]:
    return mission_status
