"""SSH falso de un Unitree G1 EDU, para probar "Añadir robot" sin hardware.

Hace de la computadora de desarrollo del G1 (en el robot real, 192.168.123.164:22):
  - acepta usuario y contraseña (de fabrica unitree / 123),
  - responde al unico comando que ejecuta la app, `lsusb`, como si la camara
    RealSense D435i de la cabeza estuviera conectada; cualquier otro comando se rechaza.

El estado del robot por DDS (rt/lowstate) lo publica el G1 simulado en MuJoCo
(Documents\\g1-simulador\\iniciar_simulador.bat, que tambien arranca este script).

Uso (desde la carpeta del backend):
    python simulador/robot_simulado.py
    python simulador/robot_simulado.py --sin-camara     (para ver el fallo del paso Camara)

En la app: IP 127.0.0.1, puerto SSH 2222, interfaz Loopback y Domain ID 1.
"""
import argparse
import logging
import os
import socket
import sys
import threading
import time

sys.dont_write_bytecode = True

LSUSB_CON_CAMARA = (
    "Bus 001 Device 001: ID 1d6b:0002 Linux Foundation 2.0 root hub\n"
    "Bus 002 Device 003: ID 8086:0b3a Intel Corp. Intel(R) RealSense(TM) Depth Camera 435i\n"
)
LSUSB_SIN_CAMARA = "Bus 001 Device 001: ID 1d6b:0002 Linux Foundation 2.0 root hub\n"


def servir_ssh(ip, puerto, usuario, clave, con_camara):
    import paramiko

    # la prueba de "Red" abre y cierra el puerto sin hablar SSH: no es un error
    logging.getLogger("paramiko").setLevel(logging.CRITICAL)

    llave = paramiko.RSAKey.generate(2048)

    class Servidor(paramiko.ServerInterface):
        def __init__(self):
            self.comando = None
            self.listo = threading.Event()

        def get_allowed_auths(self, username):
            return "password"

        def check_auth_password(self, username, password):
            ok = username == usuario and password == clave
            print(f"[ssh] inicio de sesion de «{username}»: {'aceptado' if ok else 'rechazado'}", flush=True)
            return paramiko.AUTH_SUCCESSFUL if ok else paramiko.AUTH_FAILED

        def check_channel_request(self, kind, chanid):
            return paramiko.OPEN_SUCCEEDED if kind == "session" else paramiko.OPEN_FAILED_ADMINISTRATIVELY_PROHIBITED

        def check_channel_exec_request(self, channel, command):
            self.comando = command.decode(errors="replace").strip()
            self.listo.set()
            return True  # se responde en `atender`; sin consola interactiva

    def atender(cliente):
        try:
            t = paramiko.Transport(cliente)
            t.add_server_key(llave)
            servidor = Servidor()
            t.start_server(server=servidor)
            canal = t.accept(20)
            if canal is not None and servidor.listo.wait(10):
                if servidor.comando == "lsusb":
                    print("[ssh] comando lsusb (solo lectura)", flush=True)
                    canal.sendall((LSUSB_CON_CAMARA if con_camara else LSUSB_SIN_CAMARA).encode())
                    canal.send_exit_status(0)
                else:
                    print(f"[ssh] comando rechazado: {servidor.comando!r}", flush=True)
                    canal.sendall_stderr(b"comando no permitido en el robot simulado\n")
                    canal.send_exit_status(1)
                canal.close()
            while t.is_active():
                time.sleep(0.2)
        except Exception:
            pass
        finally:
            cliente.close()

    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind((ip, puerto))
    s.listen(5)
    camara = "con" if con_camara else "SIN"
    print(f"[ssh] escuchando en {ip}:{puerto} (usuario {usuario}, {camara} camara)", flush=True)
    while True:
        cliente, _ = s.accept()
        threading.Thread(target=atender, args=(cliente,), daemon=True).start()


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--ip", default="127.0.0.1", help="IP donde escucha el robot simulado")
    p.add_argument("--ssh-puerto", type=int, default=2222)
    p.add_argument("--ssh-usuario", default="unitree")
    p.add_argument("--ssh-clave", default="123")
    p.add_argument("--sin-camara", action="store_true", help="simula que la camara no esta conectada")
    a = p.parse_args()

    try:
        servir_ssh(a.ip, a.ssh_puerto, a.ssh_usuario, a.ssh_clave, not a.sin_camara)
    except KeyboardInterrupt:
        print("Robot simulado detenido.")
        os._exit(0)


if __name__ == "__main__":
    main()
