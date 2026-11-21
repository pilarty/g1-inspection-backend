import json
from typing import List, Tuple

import threading

import numpy as np
from PIL import Image

from config import CALIBRACION_CLASIFICACION_PATH, CLASES_CLASIFICACION_PATH, MODELO_CLASIFICACION_PATH

# Las 11 clases en el orden de las salidas del modelo (EfficientNetB0 + softmax)
with open(CLASES_CLASIFICACION_PATH, encoding="utf-8") as f:
    CLASES: List[str] = json.load(f)

# Temperatura elegida en validacion (notebook de entrenamiento v3); sin archivo vale 1
TEMPERATURA = 1.0
if CALIBRACION_CLASIFICACION_PATH.exists():
    TEMPERATURA = float(json.loads(CALIBRACION_CLASIFICACION_PATH.read_text(encoding="utf-8"))["temperatura"])

# Cuántos tipos se guardan por foto (el primero es la predicción)
CANTIDAD = 3

_modelo = None
_cerrojo = threading.Lock()


def cargar():
    global _modelo
    with _cerrojo:
        if _modelo is None:
            import tensorflow as tf
            _modelo = tf.keras.models.load_model(str(MODELO_CLASIFICACION_PATH))
    return _modelo


def clasificar(imagen: Image.Image) -> List[Tuple[str, float]]:
    """Devuelve las CANTIDAD clases más probables (clase, probabilidad), de mayor a menor.
    Es softmax: las probabilidades de todas las clases suman 1 y la primera es la predicción.
    La imagen va en 224x224 y 0-255: el preprocesamiento de EfficientNet está dentro del modelo."""
    img_array = np.expand_dims(np.asarray(imagen, dtype="float32"), axis=0)
    probs = cargar().predict(img_array, verbose=0)[0]
    logits = np.log(np.clip(probs, 1e-9, 1)) / TEMPERATURA
    probs = np.exp(logits - logits.max())
    probs = probs / probs.sum()
    orden = np.argsort(probs)[::-1][:CANTIDAD]
    return [(CLASES[i], float(probs[i])) for i in orden]
