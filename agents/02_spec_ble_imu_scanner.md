# Nivel 2 — Agente Especialista #03: Escáner y Lector Bluetooth BLE IMU (`spec_ble_imu_scanner`)

- **Orquestador Padre**: `01_orch_hardware_hal`
- **Skill Especialista Asociada**: `.agent/skills/spec-ble-imu-scanner/SKILL.md`

## Responsabilidad Principal
Descubrir y conectar sensores IMU inalámbricos Bluetooth Low Energy como Movella DOT y servicios GATT genéricos de cuaterniones y batería.

## Archivos Bajo Propiedad
- `backend/hal/ble_driver.py`

## Diseño Técnico y Contrato Operativo
Usa bleak.BleakScanner para descubrir dispositivos filtrando prefijos Movella/Xsens DOT y UUIDs GATT (15172000-4947-11e9-8646-d663bd873d93). Suscribe notificaciones de cuaternión + aceleración libre y servicio de batería 0x180F con manejo seguro si no hay adaptador Bluetooth.

## Criterios de Verificación
Escaneo BLE asíncrono con respuesta controlada cuando no hay radio BLE disponible o sin sensores encendidos.
