#!/usr/bin/env bash
# ====================================================================
# NIC Timestamping Capability Probe for IEEE 1588 PTP
# Author: Glaciojtp (@Glaciojtp)
# ====================================================================

set -e

IFACE="${1:-}"
CONF_FILE="${2:-}"

if [ -z "$IFACE" ]; then
    # Auto-detect default network interface
    IFACE=$(ip route show default 2>/dev/null | awk '{print $5}' | head -n 1)
    if [ -z "$IFACE" ]; then
        IFACE="eth0"
    fi
fi

echo "===================================================="
echo " PTP Hardware & Software Timestamping Probe"
echo " Interfaz a inspeccionar: [$IFACE]"
echo "===================================================="

if ! command -v ethtool >/dev/null 2>&1; then
    echo "Error: 'ethtool' no esta instalado. Instalar con: apt-get install -y ethtool"
    exit 1
fi

if ! ip link show "$IFACE" >/dev/null 2>&1; then
    echo "Error: La interfaz '$IFACE' no existe en este sistema."
    exit 1
fi

OUTPUT=$(ethtool -T "$IFACE" 2>&1 || true)
echo "$OUTPUT"
echo "----------------------------------------------------"

HW_TX=0
HW_RX=0
HW_RAW=0

if echo "$OUTPUT" | grep -q "hardware-transmit"; then HW_TX=1; fi
if echo "$OUTPUT" | grep -q "hardware-receive"; then HW_RX=1; fi
if echo "$OUTPUT" | grep -q "hardware-raw-clock"; then HW_RAW=1; fi

PTP_DEVICE=$(echo "$OUTPUT" | grep "PTP Hardware Clock:" | awk '{print $4}' || true)

if [ "$HW_TX" -eq 1 ] && [ "$HW_RX" -eq 1 ] && [ "$HW_RAW" -eq 1 ]; then
    echo ">> [RESULTADO]: SOPORTE TOTAL DE HARDWARE TIMESTAMPING (PHY/MAC)"
    echo ">> PTP Hardware Clock Device: /dev/ptp$PTP_DEVICE"
    echo ">> Modo recomendado para ptp4l: 'time_stamping hardware'"
    MODE="hardware"
else
    echo ">> [RESULTADO]: SOPORTE DE SOFTWARE TIMESTAMPING (Fallback Linux OS)"
    echo ">> Modo recomendado para ptp4l: 'time_stamping software'"
    MODE="software"
fi

if [ -n "$CONF_FILE" ] && [ -f "$CONF_FILE" ]; then
    echo ">> Aplicando configuracion automaticamente en $CONF_FILE..."
    sed -i "s/^time_stamping.*/time_stamping           $MODE/" "$CONF_FILE"
    echo ">> Archivo actualizado con: time_stamping $MODE"
fi

echo "===================================================="
