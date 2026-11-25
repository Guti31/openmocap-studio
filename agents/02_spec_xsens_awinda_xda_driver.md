# Nivel 2 — Agente Especialista #01: Driver Xsens Awinda Doble Motor XDA + Xbus (`spec_xsens_awinda_xda_driver`)

- **Orquestador Padre**: `01_orch_hardware_hal`
- **Skill Especialista Asociada**: `.agent/skills/spec-xsens-awinda-xda-driver/SKILL.md`

## Responsabilidad Principal
Detectar de forma automática (Plug & Play cada 2 s) estaciones y dongles inalámbricos USB Xsens Awinda (`VID 0x2639`), cargar el SDK oficial (`xsensdeviceapi`) con `os.add_dll_directory()`, encender automáticamente el enlace de radio RF al conectar el USB y proveer un respaldo nativo completo por protocolo binario Xbus sobre puerto COM si el MT SDK completo no está disponible.

## Archivos Bajo Propiedad
- `backend/hal/xsens_awinda_driver.py`
- `backend/scripts/setup_xda_sdk.py`
- `backend/config/xda_paths.json`

## Diseño Técnico y Contrato Operativo
1. **Autodetección Plug & Play (2 s)**: `start_auto_monitor()` vigila puertos COM (`VID 0x2639` / descripción Xsens-Awinda) y dispositivos PnP Windows. Al detectar antena nueva, enciende automáticamente la radio a `60 Hz` TDMA usando el canal persistido (`backend/config/awinda_radio.json`, por defecto canal 11) y realiza barrido automático `[11, 15, 20, 25, ... 24]` hasta vincular los sensores MTw y guardar el canal ganador.
2. **Modo 1 (XDA Oficial)**: Lee `backend/config/xda_paths.json`, registra directorios de `xsensdeviceapi64.dll` / `xstypes64.dll` mediante `os.add_dll_directory()`, ejecuta `XsScanner_scanPorts`, `openPort()`, `gotoConfig()`, `setUpdateRate(60)`, barrido `enableRadio(channel)` hasta `childCount() > 0` y `gotoMeasurement()`.
3. **Modo 2 (Respaldo Nativo TDMA Xbus USB Serial)**: Autonegocia baudios (`921600`, `2000000`, `115200`, `460800`) y framing (`8N2` prioritario para Awinda2, respaldo `8N1`) con `timeout=0.2`, `write_timeout=0.2` y `DTR=True`/`RTS=True`. Ejecuta `WakeUp` (`FA FF 3E 00 C3`) + `GotoConfig` (`FA FF 30 00 D1`) esperando ACK real (`0x31`/`0x3F`), `ReqFWRev` (`0x12`), `ReqDID` (`0x00`), limpieza `DisableMaster` (`0xB4`→`0xB5`), tasa TDMA `60 Hz` (`cmd_set_update_rate(60)` `0xA4 00 3C` + `cmd_set_output_configuration(60)` `0xC0`), encendido de radio (`EnableMaster` `0xB2 [ch]`→`0xB3` + `GotoOperational` `0xC0`→`0xC1` + verificación `ReqRadioChannel` `0xB6`→`0xB7`, con respaldo heredado `0xAC`→`0xAD`) y `GotoMeasurement` (`0x10`→`0x11`). Si tras 3.5 s no llegan tramas de sensores MTw, rota automáticamente por los 15 canales (`11..25`) y persiste el canal ganador en `backend/config/awinda_radio.json`. Cierra `ser.close()` antes de `thread.join(timeout=1.0)`.
4. **Diagnóstico Claro en Español**: Si `Get-PnpDevice` detecta hardware `VID_2639` presente pero sin driver o sin puerto COM operativo, informa `driver_missing = True` con el mensaje: *"Antena Xsens detectada sin controlador USB. Instala el driver USB de Movella/Xsens MT Software Suite y reconecta el cable"*.

## Criterios de Verificación
- Validación exacta de tramas TDMA Xbus (`cmd_set_update_rate(60)`, `cmd_set_output_configuration(60)`, `EnableMaster`, `GotoOperational`, `DisableMaster`, `ReqRadioChannel`, `GotoMeasurement`), `SWEEP_CHANNELS` (`11..25`), persistencia en `awinda_radio.json`, sonda en vivo `COM6` (`tests/probe_awinda_live.py`) y verificación integral `tests/verify_pipeline.py`.
