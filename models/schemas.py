from typing import List

from pydantic import BaseModel


class TipoDanoIn(BaseModel):
    clase: str
    probabilidad: float  # 0 a 1


class DeteccionIn(BaseModel):
    frame: int
    timestamp: float
    x: float
    y: float
    imagen_base64: str
    prob_deteccion: float
    tipos_dano: List[TipoDanoIn]


class RoomLayoutIn(BaseModel):
    x_min: float
    x_max: float
    y_min: float
    y_max: float
    width: float
    depth: float
    floor_polygon: List[List[float]]
