from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
PESOS_DIR = BASE_DIR / "modelos_entrenados"
IMAGES_DIR = BASE_DIR / "static" / "images"

MODELO_DETECCION_PATH = PESOS_DIR / "modelo_detection.keras"
MODELO_CLASIFICACION_PATH = PESOS_DIR / "modelo_classification.keras"
THRESHOLDS_PATH = PESOS_DIR / "thresholds.json"
