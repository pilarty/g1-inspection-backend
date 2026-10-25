import os
from pathlib import Path

# Carpeta del programa: aca viven los modelos (solo lectura una vez instalado).
BASE_DIR = Path(__file__).resolve().parent
PESOS_DIR = BASE_DIR / "modelos_entrenados"

# Carpeta de datos del usuario: aca se guardan las fotos de las detecciones.
# El instalador define G1_DATA_DIR (carpeta de datos de la aplicacion del usuario);
# en desarrollo no se define y se usa la carpeta del proyecto, como hasta ahora.
DATA_DIR = Path(os.environ.get("G1_DATA_DIR") or BASE_DIR)
IMAGES_DIR = DATA_DIR / "static" / "images"

# Modelos (repo humanoid-damage-cnn, carpeta models). Se usa la v3 si sus archivos
# estan en modelos_entrenados; si no, la v2.
# - detección: CNN binaria, salida sigmoid = probabilidad de «sin daño»
# - clasificación: EfficientNetB0 con softmax sobre 11 clases
# Los *_calibracion.json (solo v3) traen la temperatura y el umbral; sin ellos
# se usa temperatura 1 y umbral 0.5, es decir, las probabilidades tal cual.
def _version(nombre: str) -> str:
    return "3" if (PESOS_DIR / f"{nombre}3.keras").exists() else "2"

_V_DET = _version("modelo_detection")
_V_CLA = _version("modelo_clasificacion")
MODELO_DETECCION_PATH = PESOS_DIR / f"modelo_detection{_V_DET}.keras"
CALIBRACION_DETECCION_PATH = PESOS_DIR / f"modelo_detection{_V_DET}_calibracion.json"
MODELO_CLASIFICACION_PATH = PESOS_DIR / f"modelo_clasificacion{_V_CLA}.keras"
CLASES_CLASIFICACION_PATH = PESOS_DIR / f"modelo_clasificacion{_V_CLA}_clases.json"
CALIBRACION_CLASIFICACION_PATH = PESOS_DIR / f"modelo_clasificacion{_V_CLA}_calibracion.json"
