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


class RoomLayoutIn(BaseModel):
    x_min: float
    x_max: float
    y_min: float
    y_max: float
    width: float
    depth: float
    floor_polygon: List[List[float]]


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
