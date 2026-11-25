---
name: global-multi-brand-hal
description: Arquitectura HAL multi-marca para unificar Xsens Awinda XDA, Serial/UART, UDP/OSC, Bluetooth BLE y simulador sintético bajo SensorPacket.
---

# Skill Global: Capa de Abstracción de Hardware Multi-Marca (HAL)

## Propósito
Permitir que OpenMocap Studio opere de forma transparente con estaciones USB Xsens Awinda y cualquier hardware IMU de terceros (ESP32, BNO085, ICM-20948, WitMotion, Movella DOT, osc/udp).

## Arquitectura
- `backend/hal/base.py`: Define `SensorPacket`, `BaseIMUDriver` (interfaz asíncrona `start()`, `stop()`, `get_status()`, `set_rate()`) y `HALManager` que multiplexa múltiples drivers activos simultáneamente.
- **Drivers soportados**:
  1. `XsensAwindaDriver`: Wrapper inteligente para `xsensdeviceapi` (`xda`) con detección de SDK en Windows, selección de canal RF `11..25` y tasa `60/100/120 Hz`.
  2. `SerialIMUDriver`: Escaneo de puertos COM con detección automática de baudios y parsers JSON, CSV, WitMotion binario `0x55` y tramas `RAW`.
  3. `UDPOSCDriver`: Socket UDP asyncio que acepta payloads JSON, CSV y mensajes OSC binarios (`/imu/<id>`).
  4. `BLEIMUDriver`: Escáner y lector GATT BLE vía `bleak` compatible con Movella DOT y características IMU estándar.
  5. `Synthetic17SensorSimulator`: Simulador biomecánico completo de 17 sensores con los IDs exactos de Awinda e inyección opcional de offsets/deriva/agitación.

## Integración con Fusión de Backup
Todo paquete recibido con `raw_only=True` pasa automáticamente por `SensorFusionBank` (filtro Madgwick/Mahony por `sensor_id`) antes de entregarse al motor de calibración.
