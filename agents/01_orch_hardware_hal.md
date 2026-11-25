# Nivel 1: Orquestador de Hardware y Capa HAL (`01_orch_hardware_hal`)

## Dominio de Responsabilidad
Garantizar que cualquier sensor IMU físico o simulado entregue paquetes `SensorPacket` normalizados a 60–120 Hz con autodetección Plug & Play de estaciones Xsens Awinda, activación automática de radio RF, respaldo nativo por protocolo binario Xbus sobre USB Serial, recuperación ante pérdidas inalámbricas y mapeo dinámico ilimitado.

## Agentes Especialistas Bajo Supervisión (6)
1. `spec_xsens_awinda_xda_driver`
2. `spec_serial_udp_multi_brand_driver`
3. `spec_ble_imu_scanner`
4. `spec_17sensor_synthetic_simulator`
5. `spec_connection_watchdog_reconnector`
6. `spec_dynamic_sensor_mapper`

## Estándar Plug & Play Xsens Awinda
- Monitoreo en segundo plano cada 2 segundos de puertos USB con `VID 0x2639` (`PID 0x0101` / `0x0102`) y dispositivos PnP Windows (`Get-PnpDevice`).
- Carga automática de DLLs nativas de Movella/Xsens mediante `os.add_dll_directory()` y rutas persistidas en `backend/config/xda_paths.json` generadas por `backend/scripts/setup_xda_sdk.py`.
- Activación automática e inmediata de radio RF (`enableRadio`) al detectar la estación conectada, utilizando XDA oficial o el motor de respaldo Xbus (`GotoConfig` `FA FF 30 00 D1`, `EnableRadio` `MID=0xAC`, `GotoMeasurement` `FA FF 10 00 F1`, decodificación `MTData2` `MID=0x36`).
- Diagnóstico explícito en español cuando el dongle físico aparece conectado sin controlador USB instalado.

## Entregables en Código
- `backend/config/default_awinda_17.json`, `backend/config/xda_paths.json`
- `backend/scripts/setup_xda_sdk.py`
- `backend/hal/base.py`, `xsens_awinda_driver.py`, `serial_udp_driver.py`, `ble_driver.py`, `synthetic_simulator.py`, `watchdog.py`, `sensor_mapper.py`
