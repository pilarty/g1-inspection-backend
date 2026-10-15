from typing import List, Optional

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


class PoseIn(BaseModel):
    x: float
    y: float
    yaw: Optional[float] = None  # radianes, hacia dónde mira el robot
    timestamp: Optional[float] = None  # time.time() del que manda; si falta, se usa la hora de llegada


class RoomLayoutIn(BaseModel):
    x_min: float
    x_max: float
    y_min: float
    y_max: float
    width: float
    depth: float
    floor_polygon: List[List[float]]
    paredes: Optional[dict] = None  # {resolucion, celdas: [[i, j], ...]} (plano de paredes del escenario)


class MissionIn(BaseModel):
    waypoints: List[List[float]]
    arrival_radius: float = 0.4
    pause_duration: float = 3.0


class MissionStatusIn(BaseModel):
    x: float
    y: float
    yaw: float
    waypoint_idx: int
    waypoints_total: int
    distance_to_goal: float
    waiting_at_waypoint: bool
    fallen: bool
