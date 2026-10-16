import uuid
from typing import List, Tuple

from models.schemas import DeteccionIn, TipoDanoIn

TRADUCCIONES = {
    # Clases del modelo de clasificación v2
    "Structural crack": "Grieta estructural",
    "Surface flaking/exfoliation": "Descascaramiento",
    "Salt weathering": "Eflorescencia salina",
    "Material loss/erosion": "Pérdida de material",
    "Moisture/water damage": "Humedad",
    "Biological growth": "Crecimiento biológico",
    "Corrosion": "Corrosión",
    "Concrete spalling": "Desprendimiento de hormigón",
    "Vegetation": "Vegetación",
    "Delamination": "Delaminación",
    "Vandalism": "Vandalismo",
    # Clases del modelo anterior (inspecciones viejas)
    "Diagonal crack": "Grieta diagonal",
    "Shear crack": "Grieta de corte",
    "Flexural/rocking crack": "Grieta de flexión",
    "Debris": "Escombros",
    "Detachment crack": "Grieta de desprendimiento",
}

def traducir(clase: str) -> str:
    return TRADUCCIONES.get(clase, clase)  # si no está en el diccionario, la deja tal cual

def armar_registro(
    det: DeteccionIn,
    ruta_imagen: str,
    prob_dano: float,
    tipos: List[Tuple[str, float]],
) -> dict:
    tipos_dano = [TipoDanoIn(clase=c, probabilidad=p) for c, p in tipos]
    return {
        "id": str(uuid.uuid4()),
        "frame": det.frame,
        "timestamp": det.timestamp,
        "x": det.x,
        "y": det.y,
        "detection_probability": round(prob_dano * 100),
        "types": [
            {
                "type": t.clase,               # clase original (inglés), para trazabilidad
                "label": traducir(t.clase),      # clase traducida, para mostrar en el front
                "probability": round(t.probabilidad * 100),
            }
            for t in tipos_dano
        ],
        "image": ruta_imagen,
    }
