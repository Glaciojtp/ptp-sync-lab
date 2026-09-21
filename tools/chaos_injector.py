#!/usr/bin/env python3
"""
HFT Network Chaos & Microburst Injector
Author: Glaciojtp (@Glaciojtp)

Simulates sudden financial market data volume spikes across the Layer 2 switch fabric
to evaluate PTP IEEE 1588v2 servo recovery and queueing jitter under severe congestion.
"""

import sys
import time
import socket
import argparse

def generate_chaos(target_ip, target_port, burst_size, duration_sec, interval_sec):
    payload = b"X" * 1400 # Max MTU frame payload
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    print("====================================================")
    print(" HFT Network Chaos & Microburst Injector")
    print(" Autor: Glaciojtp (@Glaciojtp)")
    print(f" Destino: {target_ip}:{target_port}")
    print(f" Rafaga: {burst_size} paquetes cada {interval_sec}s | Duracion: {duration_sec}s")
    print("====================================================")
    print(">> Mira tu dashboard de Grafana en tiempo real para observar")
    print(">> el impacto del buffer de conmutacion en el Offset y Jitter PTP...")

    start_time = time.time()
    burst_count = 0
    total_pkts = 0

    try:
        while time.time() - start_time < duration_sec:
            burst_count += 1
            print(f"\n[Chaos #{burst_count}] ¡Disparando microburst de {burst_size} paquetes (1400 bytes c/u)!")
            t0 = time.time()
            for _ in range(burst_size):
                sock.sendto(payload, (target_ip, target_port))
                total_pkts += 1
            elapsed = time.time() - t0
            mbps = (burst_size * 1400 * 8) / (elapsed * 1000000.0) if elapsed > 0 else 0
            print(f"[Chaos #{burst_count}] Ráfaga completada en {elapsed*1000:.2f} ms (~{mbps:.1f} Mbps)")
            print(f"[Chaos #{burst_count}] Pausa de {interval_sec}s para observar estabilizacion del servo PTP...")
            time.sleep(interval_sec)
    except KeyboardInterrupt:
        print("\n[Chaos] Interrumpido por usuario.")
    finally:
        sock.close()

    print("\n====================================================")
    print(f" Inyeccion finalizada. Total paquetes enviados: {total_pkts}")
    print("====================================================")

def main():
    parser = argparse.ArgumentParser(description="HFT Network Chaos & Switch Buffer Congester")
    parser.add_argument("-t", "--target", default="192.168.1.2", help="IP destino del host a traves del switch (default: 192.168.1.2)")
    parser.add_argument("-p", "--port", type=int, default=5001, help="Puerto UDP destino (default: 5001)")
    parser.add_argument("-b", "--burst", type=int, default=25000, help="Paquetes por ráfaga (default: 25000)")
    parser.add_argument("-d", "--duration", type=int, default=45, help="Duracion total de la prueba en segundos (default: 45)")
    parser.add_argument("-i", "--interval", type=float, default=6.0, help="Intervalo entre ráfagas en segundos (default: 6.0)")
    args = parser.parse_args()

    generate_chaos(args.target, args.port, args.burst, args.duration, args.interval)

if __name__ == "__main__":
    main()
