import base64
import io

from PIL import Image

IMG_SIZE = (224, 224)


def decodificar_y_redimensionar(imagen_base64: str) -> Image.Image:
    imagen_bytes = base64.b64decode(imagen_base64)
    imagen = Image.open(io.BytesIO(imagen_bytes)).convert("RGB")
    return imagen.resize(IMG_SIZE)
