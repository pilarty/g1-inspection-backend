import threading
import zlib

import requests
from pycognito import Cognito

from config import DATA_DIR

POOL = "us-east-1_s9afR6W9w"
CLIENT = "4044ectglilgk2u23qeit75pue"
API = "https://lunkxzh9q5.execute-api.us-east-1.amazonaws.com"

_usuario = None
relevamiento_actual = None
nombre_usuario = None
email_usuario = None
_usuario_id = None
_claims = {}


def iniciar_sesion(usuario: str, clave: str) -> None:
    """Login con Cognito (SRP). La clave no se guarda en ningun lado."""
    global _usuario, nombre_usuario, email_usuario, _usuario_id, _claims
    u = Cognito(POOL, CLIENT, username=usuario)
    u.authenticate(password=clave)
    _usuario = u
    claims = getattr(u, "id_claims", None) or {}
    _claims = dict(claims)
    nombre_usuario = claims.get("name") or claims.get("email") or usuario
    email_usuario = claims.get("email")
    _usuario_id = None


def cerrar_sesion() -> None:
    global _usuario, nombre_usuario, relevamiento_actual, email_usuario, _usuario_id, _claims
    _claims = {}
    email_usuario = None
    _usuario_id = None
    _usuario = None
    nombre_usuario = None
    relevamiento_actual = None


def perfil() -> dict:
    """Datos de la cuenta con la que se entró."""
    nombre = _claims.get("given_name")
    apellido = _claims.get("family_name")
    if nombre is None and apellido is None:
        # cuentas viejas: solo tienen «name» (o nada); se separa en nombre y apellido
        completo = _claims.get("name") or ""
        if "@" in completo:
            completo = ""
        partes = completo.split(" ", 1)
        nombre, apellido = partes[0], (partes[1] if len(partes) > 1 else "")
    return {"nombre": nombre or "", "apellido": apellido or "", "email": email_usuario, "usuario": _usuario.username,
            "mostrar": nombre_usuario}


def cambiar_datos(nombre: str, apellido: str) -> str:
    """Cambia nombre y apellido (given_name, family_name y name de Cognito). Devuelve el nombre a mostrar."""
    global nombre_usuario
    completo = f"{nombre} {apellido}".strip()
    _usuario.check_token()
    _usuario.update_profile({"given_name": nombre, "family_name": apellido, "name": completo})
    _claims.update({"given_name": nombre, "family_name": apellido, "name": completo})
    nombre_usuario = completo or email_usuario
    return nombre_usuario


def cambiar_email(email: str) -> None:
    """Pide cambiar el correo: Cognito manda un código al correo nuevo para confirmarlo."""
    _usuario.check_token()
    _usuario.update_profile({"email": email})


def confirmar_email(email: str, codigo: str) -> None:
    """Confirma el correo nuevo con el código que le llegó."""
    global email_usuario
    _usuario.check_token()
    _usuario.client.verify_user_attribute(AccessToken=_usuario.access_token, AttributeName="email", Code=codigo)
    email_usuario = email
    _claims["email"] = email


def enviar_codigo_clave(usuario: str) -> str:
    """Manda por correo un código para elegir una contraseña nueva. Devuelve a dónde (enmascarado)."""
    u = Cognito(POOL, CLIENT, username=usuario)
    r = u.client.forgot_password(ClientId=CLIENT, Username=usuario)
    return r.get("CodeDeliveryDetails", {}).get("Destination", "")


def restablecer_clave(usuario: str, codigo: str, nueva: str) -> None:
    """Pone la contraseña nueva usando el código que llegó por correo."""
    u = Cognito(POOL, CLIENT, username=usuario)
    u.client.confirm_forgot_password(ClientId=CLIENT, Username=usuario, ConfirmationCode=codigo, Password=nueva)


def registrar(nombre: str, apellido: str, email: str, clave: str) -> str:
    """Crea la cuenta en Cognito; llega un código al correo para confirmarla. Devuelve el usuario."""
    atributos = [
        {"Name": "email", "Value": email},
        {"Name": "given_name", "Value": nombre},
        {"Name": "family_name", "Value": apellido},
        {"Name": "name", "Value": f"{nombre} {apellido}".strip()},
    ]
    cliente = Cognito(POOL, CLIENT).client
    try:
        cliente.sign_up(ClientId=CLIENT, Username=email, Password=clave, UserAttributes=atributos)
        return email
    except Exception as e:
        # Si el grupo de usuarios no acepta un correo como nombre de usuario, se arma uno con el correo
        mensaje = str(e).lower()
        if "email format" not in mensaje:
            raise
    usuario = email.split("@")[0].replace(".", "_") + "_" + str(zlib.crc32(email.encode()) % 10000)
    cliente.sign_up(ClientId=CLIENT, Username=usuario, Password=clave, UserAttributes=atributos)
    return usuario


def confirmar_registro(usuario: str, codigo: str) -> None:
    Cognito(POOL, CLIENT).client.confirm_sign_up(ClientId=CLIENT, Username=usuario, ConfirmationCode=codigo)


def reenviar_codigo_registro(usuario: str) -> None:
    Cognito(POOL, CLIENT).client.resend_confirmation_code(ClientId=CLIENT, Username=usuario)


def verificar_clave(clave: str) -> None:
    """Lanza un error si la contraseña no es la de la cuenta actual."""
    Cognito(POOL, CLIENT, username=_usuario.username).authenticate(password=clave)


def eliminar_cuenta() -> None:
    """Borra el usuario de Cognito (ya no puede entrar) y cierra la sesión."""
    _usuario.check_token()
    _usuario.delete_user()
    cerrar_sesion()


def reenviar(metodo, ruta, params=None, cuerpo=None):
    """Reenvia una peticion a la API de AWS con el token de Cognito."""
    return requests.request(
        metodo, API + "/" + ruta.lstrip("/"), headers=_headers(),
        params=params, json=cuerpo, timeout=20,
    )


def usuario_id() -> int:
    """ID de la tabla usuario para quien tiene la sesion (lo crea si no existe)."""
    global _usuario_id
    if _usuario_id is not None:
        return _usuario_id
    if not email_usuario:
        raise RuntimeError("la cuenta no tiene correo")
    r = reenviar("GET", "usuarios")
    r.raise_for_status()
    for u in r.json():
        if u.get("email") == email_usuario:
            _usuario_id = u["id"]
            return _usuario_id
    r = reenviar("POST", "usuarios", cuerpo={
        "nombre": nombre_usuario or email_usuario,
        "email": email_usuario,
        "rol": "inspector",
    })
    r.raise_for_status()
    _usuario_id = r.json()["id"]
    return _usuario_id


def sesion_activa() -> bool:
    return _usuario is not None


def _headers() -> dict:
    _usuario.check_token()  # renueva el token si esta por vencer
    return {"Authorization": "Bearer " + _usuario.id_token}


def subir_hallazgo(registro: dict, relevamiento_id: int) -> None:
    """Sube la foto a S3 y crea el hallazgo en la base de datos."""
    h = _headers()
    ruta = DATA_DIR / registro["image"].lstrip("/")

    s = requests.post(
        API + "/archivos/subida", headers=h, timeout=15,
        json={"carpeta": "hallazgos", "nombre": ruta.name,
              "content_type": "image/png"},
    )
    s.raise_for_status()
    s = s.json()

    r = requests.put(s["url"], data=ruta.read_bytes(),
                     headers={"Content-Type": "image/png"}, timeout=60)
    r.raise_for_status()

    tipos = registro.get("types", [])
    r = requests.post(API + "/hallazgos", headers=h, timeout=15, json={
        "relevamiento_id": relevamiento_id,
        "tipo_dano": tipos[0]["type"] if tipos else "Sin clasificar",
        "ubicacion_x": registro["x"],
        "ubicacion_y": registro["y"],
        "imagen_representativa_url": s["key"],
        "imagenes_asociadas": [s["key"]],
        "cantidad_detecciones": 1,
        "probabilidad_promedio": registro["detection_probability"] / 100,
    })
    r.raise_for_status()


def enviar_en_segundo_plano(registro: dict, relevamiento_id: int) -> None:
    """No bloquea la deteccion local: si falla la nube, solo avisa."""
    if not sesion_activa():
        return

    def tarea():
        try:
            subir_hallazgo(registro, relevamiento_id)
        except Exception as e:
            print("[nube] no se pudo enviar el hallazgo:", e)

    threading.Thread(target=tarea, daemon=True).start()
