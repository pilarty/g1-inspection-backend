import json
from typing import List, Tuple

import numpy as np
import tensorflow as tf
from PIL import Image

from config import CLASES_CLASIFICACION_PATH, MODELO_CLASIFICACION_PATH

# Las 11 clases en el orden de las salidas del modelo (EfficientNetB0 + softmax)
with open(CLASES_CLASIFICACION_PATH, encoding="utf-8") as f:
    CLASES: List[str] = json.load(f)

# Cuántos tipos se guardan por foto (el primero es la predicción)
CANTIDAD = 3

_modelo = tf.keras.models.load_model(str(MODELO_CLASIFICACION_PATH))


def clasificar(imagen: Image.Image) -> List[Tuple[str, float]]:
    """Devuelve las CANTIDAD clases más probables (clase, probabilidad), de mayor a menor.
    Es softmax: las probabilidades de todas las clases suman 1 y la primera es la predicción.
    La imagen va en 224x224 y 0-255: el preprocesamiento de EfficientNet está dentro del modelo."""
    img_array = np.expand_dims(tf.keras.utils.img_to_array(imagen), axis=0)
    probs = _modelo.predict(img_array, verbose=0)[0]
    orden = np.argsort(probs)[::-1][:CANTIDAD]
    return [(CLASES[i], float(probs[i])) for i in orden]
