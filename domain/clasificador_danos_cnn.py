import json
from typing import List, Tuple

import numpy as np
import tensorflow as tf
from PIL import Image

from config import MODELO_CLASIFICACION_PATH, THRESHOLDS_PATH

CLASES = [
    "Diagonal crack",
    "Concrete spalling",
    "Corrosion",
    "Shear crack",
    "Flexural/rocking crack",
    "Debris",
    "Detachment crack",
]

_modelo = tf.keras.models.load_model(str(MODELO_CLASIFICACION_PATH))

with open(THRESHOLDS_PATH) as f:
    _umbrales = json.load(f)


def clasificar(imagen: Image.Image) -> List[Tuple[str, float]]:
    """Devuelve (clase, probabilidad) para las clases que superan su
    umbral, ordenadas de mayor a menor probabilidad."""
    img_array = tf.keras.utils.img_to_array(imagen)
    img_array = np.expand_dims(img_array, axis=0)
    probs = _modelo.predict(img_array, verbose=0)[0]

    detectados = [
        (CLASES[i], float(probs[i]))
        for i in range(len(CLASES))
        if probs[i] > _umbrales[CLASES[i]]
    ]
    detectados.sort(key=lambda t: t[1], reverse=True)
    return detectados
