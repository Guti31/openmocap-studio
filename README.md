# OpenMocap Studio - APLICACION_TRAJE

Plataforma profesional de captura de movimiento inercial de escritorio compatible con estaciones inalámbricas **Xsens Awinda** y extensible a **cualquier IMU de terceros** (Serial/UART, Wi-Fi UDP/OSC, Bluetooth BLE y simulador sintético de 17 sensores), con calibración T-Pose/N-Pose + Caminata dinámica, visor 3D a 60 FPS en estilo estudio oscuro, grabación de video `.mp4` y exportación directa a **Blender** (`.bvh` y `.fbx` compatible con Rigify y Mixamo).

## Estructura del Proyecto

- `agents/` y `.agent/`: Arquitectura multi-agente jerárquica (Nivel 0, 4 Orquestadores Nivel 1, 24 Agentes Nivel 2, 3 reglas globales y 30 skills).
- `backend/`: Motor Python FastAPI + WebSockets a 120 Hz (`hal/`, `kinematics/`, `recording/`, `export/`).
- `frontend/`: Aplicación de escritorio Electron + React + TypeScript + Tailwind + Three.js (`@react-three/fiber`) + Recharts.
- `blender_tools/`: Script automatizado `convertir_a_fbx.py` para conversión `.bvh -> .fbx` sin interfaz gráfica en Blender.
- `build/`: Configuración PyInstaller (`openmocap_backend.spec`).
- `tests/`: Suite de verificación integral (`verify_pipeline.py`).

## Uso Inmediato

### 1. Ejecutar el Estudio en Modo Escritorio
Haga doble clic o ejecute desde terminal:
```bat
INICIAR_ESTUDIO.bat
```
Al abrirse, el simulador biomecánico de 17 sensores (con los IDs Xsens Awinda predeterminados en `backend/config/default_awinda_17.json`) comienza a transmitir a 120 Hz de inmediato para pruebas sin hardware.

### 2. Conectar Hardware Real
- **Xsens Awinda USB**: Instale Movella/Xsens MT Software Suite (incluye `xsensdeviceapi`), conecte la antena USB Awinda, seleccione el canal RF (11–25) en el panel izquierdo y pulse **Conectar**.
- **ESP32 / Arduino / BNO085 / ICM-20948 / WitMotion (Serial o Wi-Fi UDP/OSC)**:
  - Puerto COM con autodetección de baudios (`115200`..`921600`) aceptando JSON, CSV, WitMotion `0x55` y tramas `RAW,ID,ax,ay,az,gx,gy,gz` (con fusión Madgwick automática).
  - Wi-Fi UDP/OSC en puerto `9000` (configurable).
- **Bluetooth BLE**: Busque sensores **Movella DOT** o IMUs GATT desde la sección BLE del panel izquierdo.
- **Sensores Adicionales y Mapeo por Agitación**: Desde la pestaña **Mapa Corporal**, agite cualquier sensor para identificarlo y asígnelo a cualquiera de los 17 huesos o añada nuevos segmentos personalizados (`21`, `32+` sensores o props).

### 3. Calibración (Correas Arbitrarias + Deriva Magnética)
1. Abra **Calibrar** en la barra superior.
2. Elija **T-Pose** o **N-Pose** y capture 4 segundos estáticos.
3. Ejecute la **Caminata Dinámica** de 6 segundos en línea recta; el motor estima automáticamente los ejes funcionales sagitales y elimina la deriva magnética interior por sensor.

### 4. Exportar para Blender y Video MP4
- **Tomas `.omocap`**: Grabe en la barra inferior y recorte con `Inicio [` y `Fin ]`.
- **Blender `.bvh` / `.fbx`**: Pulse **Exportar Blender**, elija convención `OpenMocap`, `Mixamo` o `Rigify`, exporte `.bvh` o convierta directamente a `.fbx` si Blender está instalado en el sistema (o indicando `blender.exe`).
- **Video `.mp4`**: Pulse **Grabar Video MP4** en la barra superior para capturar el visor 3D a 60 FPS con o sin telemetría superpuesta.

## Generar Instalador `.exe` Distribuible
```bat
GENERAR_INSTALADOR.bat
```
Generará el ejecutable backend con PyInstaller y el instalador Windows NSIS dentro de `dist_installer/`.

## Verificación Automatizada
```bat
backend\.venv\Scripts\python.exe tests\verify_pipeline.py
```

