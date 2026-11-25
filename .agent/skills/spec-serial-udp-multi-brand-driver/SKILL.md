---
name: spec-serial-udp-multi-brand-driver
description: Ingerir placas e IMUs de terceros (ESP32, BNO085, ICM-20948, WitMotion, Arduino) tanto por puerto serie COM/USB como por red local Wi-Fi UDP/OSC.
---

# Skill Especialista: Driver Multi-Marca Serial UART y Wi-Fi UDP/OSC

- **Agente Propietario**: `agents/02_spec_serial_udp_multi_brand_driver.md`
- **Orquestador de Dominio**: `01_orch_hardware_hal`

## Archivos Objetivo
- `backend/hal/serial_udp_driver.py`

## Especificación Algorítmica y Contratos
Escanea puertos COM con pyserial probando baudios (115200, 921600, 57600, 230400, 38400). Decodifica JSON, CSV (quat o RAW), paquetes binarios WitMotion 0x55 (0x51 accel, 0x52 gyro, 0x53 angle, 0x59 quat) y mensajes OSC binarios (/imu/<id>). Activa raw_only=True cuando solo llegan datos crudos de acelerómetro/giroscopio.

## Criterios de Aceptación y Pruebas
Pruebas unitarias de parseo JSON, CSV, WitMotion y OSC en runtime sin bloquear el event loop.
