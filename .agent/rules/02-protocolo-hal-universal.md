# Regla Global 02: Protocolo Universal de Capa de Abstracción de Hardware (HAL)

## Esquema Canónico de Paquete (`SensorPacket`)
Todo driver de entrada (Xsens Awinda XDA, Serial/UART, Wi-Fi UDP/OSC, Bluetooth BLE o Simulador Sintético) debe emitir exclusivamente instancias válidas del esquema unificado `SensorPacket`:

| Campo | Tipo | Descripción |
|---|---|---|
| `sensor_id` | `str` | Identificador único del sensor (ej. `"00B4D904"`, `"ESP32_01"`, `"DOT_A1B2"`). |
| `brand` | `str` | Marca o familia (`"xsens_awinda"`, `"movella_dot"`, `"esp32_bno085"`, `"witmotion"`, `"generic_imu"`, `"simulator"`). |
| `protocol` | `str` | Transporte (`"xda"`, `"serial"`, `"udp"`, `"osc"`, `"ble"`, `"synthetic"`). |
| `segment` | `str` | Segmento asignado o `"UNASSIGNED"` si aún no está mapeado. |
| `quaternion` | `list[float]` | Cuaternión `[w, x, y, z]` normalizado (sensor a mundo provisional del sensor). |
| `free_accel` | `list[float]` | Aceleración lineal libre `[ax, ay, az]` en `m/s^2` expresada en el **marco mundo provisional del sensor** (Y-up). |
| `gyro` | `list[float]` | Velocidad angular `[gx, gy, gz]` en `rad/s` expresada en el **marco local del sensor**. |
| `mag` | `list[float]` | Campo magnético normalizado o uT `[mx, my, mz]` en marco local del sensor. |
| `battery` | `float` | Porcentaje `0.0 - 100.0` (o `-1.0` si no reporta batería). |
| `rssi` | `int` | Potencia de señal en dBm (ej. `-45`, o `0` si es cableado). |
| `hz` | `float` | Frecuencia efectiva medida en tiempo real para este sensor. |
| `timestamp_ms` | `float` | Marca temporal monotónica en milisegundos. |
| `raw_only` | `bool` | `True` si `quaternion` es identidad y requiere fusión Madgwick/Mahony en el backend. |

## Reglas Operativas del HAL
1. **Desacoplamiento por marcas**: Ningún módulo de cinemática o interfaz puede importar librerías específicas de fabricante (`xsensdeviceapi`, `pyserial`, `bleak`); todo fluye a través de `HALManager` y `SensorPacket`.
2. **Estabilidad inalámbrica**: `ConnectionWatchdog` supervisa tiempos entre paquetes; ante microcortes `< 250 ms` realiza interpolación predictiva mediante velocidad angular (`gyro`), evitando saltos en el esqueleto.
3. **Escalabilidad de nodos**: El mapa de sensores acepta los 17 nodos base de cuerpo completo y cualquier cantidad adicional de sensores (`21`, `32+`) en segmentos secundarios o props sin modificar el protocolo.
