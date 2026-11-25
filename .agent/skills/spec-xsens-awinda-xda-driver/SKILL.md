---
name: spec-xsens-awinda-xda-driver
description: Autodetección Plug & Play USB (VID 0x2639) para Xsens Awinda, carga DLL con os.add_dll_directory(), activación automática de radio RF en XDA oficial y respaldo nativo por protocolo binario Xbus sobre USB Serial.
---

# Skill Especialista: Driver Xsens Awinda Doble Motor (XDA + Xbus Serial)

- **Agente Propietario**: `agents/02_spec_xsens_awinda_xda_driver.md`
- **Orquestador de Dominio**: `01_orch_hardware_hal`

## Archivos Objetivo
- `backend/hal/xsens_awinda_driver.py`
- `backend/scripts/setup_xda_sdk.py`
- `backend/config/xda_paths.json`

## Especificación Algorítmica y Contratos
1. **Búsqueda de SDK Local (`setup_xda_sdk.py`)**: Escanea `backend/xda_sdk/`, unidades locales (`C:\`, `D:\`...), `Downloads`, `AppData` y rutas `Movella/Xsens` buscando wheels `xsensdeviceapi*.whl` compatibles y DLLs nativas (`xsensdeviceapi64.dll`, `xstypes64.dll`) para persistir rutas en `backend/config/xda_paths.json`.
2. **Carga Segura de DLLs y Sincronización XDA**: Registra cada carpeta con `os.add_dll_directory()` y, cuando XDA está disponible, abre `XsControl`, ejecuta `gotoConfig()`, `setUpdateRate(60)`, barrido `enableRadio(ch)` (`[11, 15, 20, 25, ... 24]`) hasta `childCount() > 0` y `gotoMeasurement()`.
3. **Respaldo Nativo TDMA Xbus Bidireccional sobre USB Serial (`VID 0x2639`)**:
   - Autonegociación real en `(921600, 2000000, 115200, 460800)` con `8N2` prioritario y respaldo `8N1`, `timeout=0.2`, `write_timeout=0.2`, sin `.flush()`, `DTR=True`, `RTS=True`.
   - Secuencia TDMA 60 Hz: `WakeUp` (`0x3E`), `GotoConfig` (`0x30`→`0x31`), `ReqFWRev` (`0x12`), `ReqDID` (`0x00`), `DisableMaster` (`0xB4`→`0xB5`), `SetUpdateRate(60)` (`0xA4 00 3C`), `SetOutputConfiguration(60)` (`0xC0`), `EnableMaster` (`0xB2 [ch]`→`0xB3`) + `GotoOperational` (`0xC0`→`0xC1`) + `ReqRadioChannel` (`0xB6`→`0xB7 [00 ch]`) (respaldo `0xAC`→`0xAD`) y `GotoMeasurement` (`0x10`→`0x11`).
   - Barrido automático RF (`11..25`) cada `3.5 s` si aún no vincula ningún MTw, persistiendo el canal ganador en `backend/config/awinda_radio.json`.
   - Cierre seguro en `stop()` cerrando el puerto serial antes de `thread.join(timeout=1.0)`.
   - Parser `XbusStreamParser` + `parse_mtdata2_payload` para bloques `MTData2` (`MID = 0x36`).
4. **Monitor Automático Plug & Play (2 s)**: Enciende la radio en cuanto detecta la estación USB, y si Windows reporta dispositivo presente sin driver COM (`Get-PnpDevice`), reporta estado `driver_missing` con guía en español.

## Criterios de Aceptación y Pruebas
- Pruebas en `tests/verify_pipeline.py` validando checksums Xbus exactos, decodificación `MTData2` -> `SensorPacket` Y-up, y estado vivo del monitor automático en `/api/hardware/awinda/status`.
