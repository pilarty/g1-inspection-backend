import base64
import uuid

from config import IMAGES_DIR

IMAGES_DIR.mkdir(parents=True, exist_ok=True)


def guardar_imagen(imagen_base64: str) -> str:
    """Guarda la imagen recibida en base64 y devuelve la ruta pública.
    Hoy guarda en disco local (static/images); cuando pasen a producción,
    esto se reemplaza por un upload a S3 sin tocar el resto del código."""
    nombre_imagen = f"{uuid.uuid4().hex}.png"
    (IMAGES_DIR / nombre_imagen).write_bytes(base64.b64decode(imagen_base64))
    return f"/static/images/{nombre_imagen}"
