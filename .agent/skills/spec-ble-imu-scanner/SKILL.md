---
name: spec-ble-imu-scanner
description: Descubrir y conectar sensores IMU inalámbricos Bluetooth Low Energy como Movella DOT y servicios GATT genéricos de cuaterniones y batería.
---

# Skill Especialista: Escáner y Lector Bluetooth BLE IMU

- **Agente Propietario**: `agents/02_spec_ble_imu_scanner.md`
- **Orquestador de Dominio**: `01_orch_hardware_hal`

## Archivos Objetivo
- `backend/hal/ble_driver.py`

## Especificación Algorítmica y Contratos
Usa bleak.BleakScanner para descubrir dispositivos filtrando prefijos Movella/Xsens DOT y UUIDs GATT (15172000-4947-11e9-8646-d663bd873d93). Suscribe notificaciones de cuaternión + aceleración libre y servicio de batería 0x180F con manejo seguro si no hay adaptador Bluetooth.

## Criterios de Aceptación y Pruebas
Escaneo BLE asíncrono con respuesta controlada cuando no hay radio BLE disponible o sin sensores encendidos.
