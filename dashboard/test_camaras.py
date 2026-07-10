"""Diagnóstico local de cámaras OpenCV en Windows (índices 0 a 4)."""

import os
import time

os.environ["OPENCV_VIDEOIO_PRIORITY_OBSENSOR"] = "0"
import cv2

try:
    from pygrabber.dshow_graph import FilterGraph
except ImportError:
    FilterGraph = None


USB_CAMERA_INDEX = 0
OBS_CAMERA_INDEX = 1


def crear_captura(indice, metodo):
    if metodo == "DSHOW_2_ARGS":
        return cv2.VideoCapture(indice, cv2.CAP_DSHOW)
    if metodo == "DSHOW_SUM":
        return cv2.VideoCapture(cv2.CAP_DSHOW + indice)
    if metodo == "MSMF":
        return cv2.VideoCapture(indice, cv2.CAP_MSMF)
    return cv2.VideoCapture(indice)


def probar_camara(indice, nombre_backend, metodo):
    print(f"[PRUEBA] Índice {indice} con backend {nombre_backend}")
    captura = crear_captura(indice, metodo)
    try:
        if not captura.isOpened():
            print("  No se pudo abrir")
            return False

        captura.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        captura.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        captura.set(cv2.CAP_PROP_FPS, 20)

        for _ in range(10):
            disponible, frame = captura.read()
            if disponible and frame is not None and frame.size:
                alto, ancho = frame.shape[:2]
                print(f"  Cámara detectada: frame {ancho}x{alto}")
                return True
            time.sleep(0.1)

        print("  Abrió el dispositivo, pero no se pudo leer ningún frame")
        return False
    finally:
        captura.release()
        time.sleep(0.2)


def main():
    nombres = []
    if FilterGraph is not None:
        try:
            nombres = FilterGraph().get_input_devices()
        except Exception as error:
            print(f"No se pudieron enumerar nombres DirectShow: {error}")

    print("=== DISPOSITIVOS DIRECTSHOW ===")
    if nombres:
        for indice, nombre in enumerate(nombres):
            tipo = "OBS VIRTUAL (NO USAR)" if "obs" in nombre.casefold() else "FÍSICA"
            print(f"Índice {indice}: {nombre} [{tipo}]")
    else:
        print("No fue posible obtener nombres; se probarán los índices.")
    print()

    metodos = (
        ("DSHOW (índice y backend)", "DSHOW_2_ARGS"),
        ("DSHOW (backend + índice)", "DSHOW_SUM"),
        ("MSMF", "MSMF"),
        ("AUTO", "AUTO"),
    )
    detectadas = []
    for indice in range(5):
        for nombre_backend, metodo in metodos:
            if probar_camara(indice, nombre_backend, metodo):
                detectadas.append((indice, nombre_backend))

    print("\n=== RESULTADO ===")
    if detectadas:
        for indice, backend in detectadas:
            nombre = nombres[indice] if indice < len(nombres) else "Nombre desconocido"
            advertencia = " — ADVERTENCIA: OBS Virtual Camera" if "obs" in nombre.casefold() else ""
            print(f"Índice {indice}: {nombre}, disponible con {backend}{advertencia}")
    else:
        print("No se detectó ninguna cámara entre los índices 0 y 4.")

    if any(indice == OBS_CAMERA_INDEX for indice, _backend in detectadas):
        print("ADVERTENCIA: OBS Virtual Camera está disponible, pero el proyecto no la usará.")
    if not any(indice == USB_CAMERA_INDEX for indice, _backend in detectadas):
        print("Cámara USB física no disponible.")


if __name__ == "__main__":
    main()
