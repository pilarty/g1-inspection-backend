import uuid

from domain.evaluador_severidad import calcular_severidad
from models.schemas import DeteccionIn

# Traducción de las clases del modelo (en inglés, tal como salió del
# entrenamiento) al español, para mostrar en el front. Se guarda también
# la clase original sin traducir, para trazabilidad (RNF4).
TRADUCCIONES = {
    "Diagonal crack": "Grieta diagonal",
    "Concrete spalling": "Desprendimiento de hormigón",
    "Corrosion": "Corrosión",
    "Shear crack": "Grieta de corte",
    "Flexural/rocking crack": "Grieta de flexión",
    "Debris": "Escombros",
    "Detachment crack": "Grieta de desprendimiento",
}


def traducir(clase: str) -> str:
    return TRADUCCIONES.get(clase, clase)  # si no está en el diccionario, la deja tal cual


def armar_registro(det: DeteccionIn, ruta_imagen: str) -> dict:
    return {
        "id": str(uuid.uuid4()),
        "frame": det.frame,
        "timestamp": det.timestamp,
        "x": det.x,
        "y": det.y,
        "severity": calcular_severidad(det.tipos_dano),
        "types": [
            {
                "type": t.clase,               # clase original (inglés), para trazabilidad
                "label": traducir(t.clase),      # clase traducida, para mostrar en el front
                "probability": round(t.probabilidad * 100),
            }
            for t in det.tipos_dano
        ],
        "image": ruta_imagen,
    }
