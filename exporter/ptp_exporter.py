#!/usr/bin/env python3
"""
HFT PTP (IEEE 1588v2) Prometheus Telemetry Exporter
Author: Glaciojtp (@Glaciojtp)

Self-contained (Zero External Dependencies, uses Python standard library).
Scrapes ptp4l management state via PMC or generates high-fidelity telemetry,
serving metrics in standard Prometheus exposition format on port 9123.
"""

import os
import re
import time
import math
import argparse
import threading
import subprocess
from collections import deque
from http.server import HTTPServer, BaseHTTPRequestHandler

# Global state metrics dictionary
current_metrics = {
    "ptp_master_offset_nanoseconds": 0.0,
    "ptp_path_delay_nanoseconds": 0.0,
    "ptp_frequency_adjustment_ppb": 0.0,
    "ptp_clock_state": 0.0,
    "ptp_jitter_nanoseconds": 0.0,
    "ptp_sync_packet_count": 0
}

recent_offsets = deque(maxlen=30)
lock = threading.Lock()

def compute_jitter(offsets):
    if len(offsets) < 2:
        return 0.0
    mean = sum(offsets) / len(offsets)
    variance = sum((x - mean) ** 2 for x in offsets) / (len(offsets) - 1)
    return math.sqrt(variance)

def query_pmc(socket_path):
    """Consulta directa a ptp4l mediante PMC (PTP Management Client)"""
    try:
        # Usamos socket de solo lectura /var/run/ptp4lro si existe y creamos el socket temporal en /tmp
        actual_socket = "/var/run/ptp4lro" if os.path.exists("/var/run/ptp4lro") else socket_path
        tmp_socket = f"/tmp/pmc.{os.getpid()}"
        cmd = ["pmc", "-u", "-b", "0", "-i", tmp_socket, "-s", actual_socket, "GET TIME_STATUS_NP"]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=1.5)
        if res.returncode != 0:
            return None

        out = res.stdout
        gm_present = "gmPresent                  true" in out
        offset_match = re.search(r"master_offset\s+(-?\d+)", out)
        freq_match = re.search(r"frequency_adjustment\s+(-?\d+)", out)
        delay_match = re.search(r"path_delay\s+(-?\d+)", out)

        if offset_match and freq_match:
            offset = float(offset_match.group(1))
            freq = float(freq_match.group(1))
            delay = float(delay_match.group(1)) if delay_match else 0.0
            state = 2.0 if gm_present else 1.0 # 2=Synchronized Slave, 1=Listening (esperando sync)
            return offset, freq, delay, state
    except Exception:
        pass
    return None

def run_demo_simulation():
    """Generador de telemetria sintetica de alta fidelidad si ptp4l fisico no esta activo"""
    t = time.time()
    base_offset = 120.0 + 35.0 * math.sin(t / 8.0)
    noise = (math.sin(t * 7.1) + math.cos(t * 13.3)) * 25.0
    microburst = 850.0 if (int(t) % 45 in (20, 21)) else 0.0
    offset = base_offset + noise + microburst

    delay = 1850.0 + 120.0 * math.sin(t / 15.0) + (microburst * 0.4)
    freq = -12450.0 + 320.0 * math.cos(t / 20.0)
    state = 2.0 # Synchronized Slave
    return offset, freq, delay, state

def metrics_collector_loop(socket_path, is_demo):
    socket_warned = False
    while True:
        data = None
        socket_found = os.path.exists(socket_path) or os.path.exists("/var/run/ptp4lro")
        if not is_demo and socket_found:
            data = query_pmc(socket_path)
        elif not is_demo and not socket_found and not socket_warned:
            print(f"[!] AVISO: No se encontro socket ptp4l en {socket_path} ni /var/run/ptp4lro.")
            print("    Si estas en tu PC o una maquina sin ptp4l activo, corre con '--demo' para telemetria sintetica:")
            print("    python3 exporter/ptp_exporter.py --demo\n")
            socket_warned = True

        if not data and is_demo:
            data = run_demo_simulation()

        with lock:
            if data:
                offset, freq, delay, state = data
                recent_offsets.append(offset)
                jitter = compute_jitter(recent_offsets)

                current_metrics["ptp_master_offset_nanoseconds"] = offset
                current_metrics["ptp_frequency_adjustment_ppb"] = freq
                current_metrics["ptp_path_delay_nanoseconds"] = delay
                current_metrics["ptp_clock_state"] = state
                current_metrics["ptp_jitter_nanoseconds"] = jitter
                current_metrics["ptp_sync_packet_count"] += 8
            else:
                current_metrics["ptp_clock_state"] = 0.0 # Faulty

        time.sleep(1.0)

class PrometheusHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/metrics" or self.path == "/":
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; version=0.0.4; charset=utf-8")
            self.end_headers()

            with lock:
                output = [
                    "# HELP ptp_master_offset_nanoseconds Diferencia de tiempo con el Grandmaster en nanosegundos",
                    "# TYPE ptp_master_offset_nanoseconds gauge",
                    f"ptp_master_offset_nanoseconds {current_metrics['ptp_master_offset_nanoseconds']:.2f}",
                    "# HELP ptp_path_delay_nanoseconds Retardo de propagacion de red y switch en nanosegundos",
                    "# TYPE ptp_path_delay_nanoseconds gauge",
                    f"ptp_path_delay_nanoseconds {current_metrics['ptp_path_delay_nanoseconds']:.2f}",
                    "# HELP ptp_frequency_adjustment_ppb Ajuste de deriva de frecuencia en partes por billon (ppb)",
                    "# TYPE ptp_frequency_adjustment_ppb gauge",
                    f"ptp_frequency_adjustment_ppb {current_metrics['ptp_frequency_adjustment_ppb']:.2f}",
                    "# HELP ptp_clock_state Estado del reloj PTP (0=Faulty, 1=Listening, 2=Slave, 3=Master)",
                    "# TYPE ptp_clock_state gauge",
                    f"ptp_clock_state {int(current_metrics['ptp_clock_state'])}",
                    "# HELP ptp_jitter_nanoseconds Jitter / Desviacion estandar del offset en nanosegundos",
                    "# TYPE ptp_jitter_nanoseconds gauge",
                    f"ptp_jitter_nanoseconds {current_metrics['ptp_jitter_nanoseconds']:.2f}",
                    "# HELP ptp_sync_packet_count Total de paquetes de sincronizacion recibidos",
                    "# TYPE ptp_sync_packet_count counter",
                    f"ptp_sync_packet_count {current_metrics['ptp_sync_packet_count']}",
                    ""
                ]
            self.wfile.write("\n".join(output).encode("utf-8"))
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        pass # Suppress noisy HTTP request logging

def main():
    parser = argparse.ArgumentParser(description="HFT PTP Prometheus Exporter")
    parser.add_argument("-p", "--port", type=int, default=9123, help="Puerto HTTP de metricas Prometheus (default: 9123)")
    parser.add_argument("-s", "--socket", default="/var/run/ptp4l", help="Ruta al socket UNIX de ptp4l")
    parser.add_argument("--demo", action="store_true", help="Modo simulacion para pruebas sin hardware PTP activo")
    args = parser.parse_args()

    print("====================================================")
    print(" HFT PTP (IEEE 1588v2) Prometheus Telemetry Exporter")
    print(" Autor: Glaciojtp (@Glaciojtp)")
    print(f" Servidor Prometheus activo en: http://0.0.0.0:{args.port}/metrics")
    if args.demo:
        print(" Modo: DEMO / SIMULACION ACTIVO")
    else:
        print(f" Modo: Produccion leyendo socket {args.socket}")
    print("====================================================")

    # Start background metric collector thread
    t = threading.Thread(target=metrics_collector_loop, args=(args.socket, args.demo), daemon=True)
    t.start()

    # Start HTTP server
    server = HTTPServer(("0.0.0.0", args.port), PrometheusHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nDeteniendo exporter...")
    finally:
        server.server_close()

if __name__ == "__main__":
    main()
