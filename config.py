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

MODELO_DETECCION_PATH = PESOS_DIR / "modelo_detection.keras"
MODELO_CLASIFICACION_PATH = PESOS_DIR / "modelo_classification.keras"
THRESHOLDS_PATH = PESOS_DIR / "thresholds.json"
