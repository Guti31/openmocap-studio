# Reporte de Auditoría Técnica Completa — OpenMocap Studio (`APLICACION_TRAJE`)

- **Rol auditor**: Orquestador Director Maestro (`00_master_director_orchestrator`)
- **Alcance**: 100 % del proyecto — 4 Orquestadores de Nivel 1, 24 Agentes Especialistas de Nivel 2, código fuente real en `backend/`, `frontend/`, `blender_tools/`, `build/`, `tests/`, `backend/config/`, `dist/`, `dist_installer/` y scripts `.bat`.
- **Modo de auditoría**: Solo lectura / diagnóstico (cero archivos de código/configuración modificados, cero aperturas de `COM6` ni llamadas a `XsScanner`).

---

## 1. RESUMEN EJECUTIVO DE MADUREZ

### Madurez por Dominio / Módulo

| Dominio / Orquestador | Madurez | Estado General | Resumen Técnico |
| :--- | :---: | :---: | :--- |
| **Dominio 1 — Hardware y Capa HAL** (`01_orch_hardware_hal`, Agentes #01–#06) | **62 %** | 🔴 CRÍTICO | El simulador sintético de 17 sensores y los parsers base funcionan bien, pero el puente físico Xsens Awinda (`xda_bridge_worker.py`) bloquea la estación `01210CE2` en **Modo Config** (LED fijo, 0 paquetes) tras detectar `16/17` sensores; además `ConnectionWatchdog` y `SensorMapper` carecen de `threading.Lock`. |
| **Dominio 2 — Cinemática, Fusión y Calibración** (`02_orch_kinematics_calibration`, Agentes #07–#12) | **82 %** | 🟠 ADVERTENCIA / CRÍTICO | Álgebra de cuaterniones Hamilton `[w,x,y,z]`, conversión ENU→Y-up, FK jerárquico con piso `Y>=0` y calibración estática MTw realista están bien estructurados; pero existen 2 fallas biomecánicas serias: inversión ±180° en PCA de caminata si el sujeto no camina dentro de ±90° de `+Z` y eje duplicado en flexión/rotación de codos. |
| **Dominio 3 — Estudio 3D e Interfaz Electron/React** (`03_orch_studio_3d_ui`, Agentes #13–#18) | **76 %** | 🔴 CRÍTICO | El flujo visual de 4 pasos, WebSocket 60–120 Hz desacoplado (`liveFrameRef`) y Three.js están bien encaminados; pero `electron/main.cjs` tiene un **deadlock de buffer de pipe** (`stdout`/`stderr` sin drenar) que congela el backend en Windows, hay contradicción visual (`16/17 Listos` vs `0/17 activos`), y el selector rápido de estatura borra medidas antropométricas opcionales. |
| **Dominio 4 — Exportación, Video y Empaquetado `.exe`** (`04_orch_export_packaging`, Agentes #19–#24) | **54 %** | 🔴 CRÍTICO | La exportación BVH estructural y la suite sintética QA pasan, pero **el instalador `.exe` actual (`166 MB`) NO puede operar un traje Xsens físico en otra PC**: compila con Python 3.12 sin `xsensdeviceapi`, sin las 7 DLLs de `dll64/`, sin `xda_bridge_worker.py`/Python 3.10, con rutas absolutas `C:\APLICACION_TRAJE\...` y escritura en `Program Files`. Además FFmpeg/Blender bloquean el event loop `async`. |
| **MADUREZ GLOBAL DEL PROYECTO** | **68.5 %** | 🔴 BLOQUEADO PARA PRODUCCIÓN | Apto para demostración sintética local en desarrollo; **bloqueado para captura física real con Xsens Awinda y para distribución `.exe` a terceros** hasta resolver los 7 bloqueos críticos detallados en la Sección 3. |

### Bloqueo Principal (Causa Raíz Exacta del Síntoma en `COM6` / `01210CE2`)

Cuando conectas la antena **Xsens Awinda (`station_id: 01210CE2` en `COM6`)**, el puente oficial [`xda_bridge_worker.py`](file:///c:/APLICACION_TRAJE/backend/hal/xda_bridge_worker.py) detecta hasta `16/17` sensores MTw en el canal RF 11, pero **la estación queda congelada en Modo Config (LED sólido sin parpadear) emitiendo `0` paquetes (`0 / 17 conectados` en el panel izquierdo y maniquí congelado en T-Pose)**.

La auditoría línea por línea frente al ejemplo oficial [`Example_mtw.cs`](file:///c:/APLICACION_TRAJE/backend/xda_sdk/examples/Example_mtw.cs) confirmó una **cadena de 5 errores simultáneos en `xda_bridge_worker.py`**:
1. **Llamadas indebidas y duplicadas a `setOutputConfiguration()` en Awinda2 MTw**: `Example_mtw.cs` (líneas 110–162) **jamás** invoca `master.setOutputConfiguration()` ni `child.setOutputConfiguration()` (el protocolo inalámbrico TDMA de Awinda2/MTw2 no se configura por XDI, solo con `master.setUpdateRate(60)` y `enableRadio(ch)`). En [`xda_bridge_worker.py:460-486,635-640`](file:///c:/APLICACION_TRAJE/backend/hal/xda_bridge_worker.py#L460-L486), además de invocarlo en el maestro, `cand_devs` combina `master.children()` + `connectivity_devices.values()` **sin deduplicar por `sid`**, disparando **32–34 transacciones RF bloqueantes (`setOutputConfiguration` ×2 por sensor)** más **16–17 `requestBatteryLevel()`** justo antes de `gotoMeasurement()`.
2. **Transición prematura sin esperar inicialización de todos los MTw**: [`xda_bridge_worker.py:598-629`](file:///c:/APLICACION_TRAJE/backend/hal/xda_bridge_worker.py#L598-L629) usa un temporizador fijo de 4.0 s contado desde el **primer** sensor (no reinicia al llegar el 2.º..16.º) y nunca invoca `master.waitForAllDevicesInitialized()` (disponible en `xsensdeviceapi` SWIG).
3. **Deadlock silencioso al fallar `gotoMeasurement()`**: En [`xda_bridge_worker.py:642-699`](file:///c:/APLICACION_TRAJE/backend/hal/xda_bridge_worker.py#L642-L699), si `master.gotoMeasurement()` devuelve `False` en los 3 intentos rápidos (espaciados apenas `0.4 s` mientras los 16 MTw siguen ocupados con RF), el worker emite `antenna_state="radio_on"`, `measurement_ack=False` con el mensaje engañoso `"Motor Oficial XDA Activo · Canal RF 11 · 16/17 Sensores"` y entra en un bucle `while not stop_event.is_set()` **sin reintentar jamás `gotoMeasurement()` ni reportar error**.
4. **Punteros SWIG obsoletos y cuádruple registro de callbacks**: `connectivity_devices[sid] = dev` ([línea 236](file:///c:/APLICACION_TRAJE/backend/hal/xda_bridge_worker.py#L236)) guarda punteros temporales de C++ sin limpiarlos al desconectarse ([líneas 237–238](file:///c:/APLICACION_TRAJE/backend/hal/xda_bridge_worker.py#L237-L238)), y adjuntar `_MtwCallback` (con `onLiveDataAvailable` **y** `onAllDataAvailable`) tanto al maestro como a cada hijo genera hasta 4 disparos SWIG/GIL por paquete.
5. **Contradicción de métricas en UI y ocultamiento de diagnósticos**: [`xsens_awinda_driver.py:983-1093`](file:///c:/APLICACION_TRAJE/backend/hal/xsens_awinda_driver.py#L983-L1093) descarta silenciosamente todos los eventos `"type": "debug"` del worker; mientras [`TopBar.tsx:98`](file:///c:/APLICACION_TRAJE/frontend/src/components/TopBar.tsx#L98) muestra `awinda.connected_sensor_count` (`16/17 Sensores Listos`), [`LeftHardwarePanel.tsx:257,359`](file:///c:/APLICACION_TRAJE/frontend/src/components/LeftHardwarePanel.tsx#L257) muestra `onlineCount` del watchdog (`0/17 activos`).

---

## 2. TABLA DE AUDITORÍA DE LOS 24 AGENTES

| # | Agente Especialista (Nivel 2) | Orquestador Padre | Archivos Revisados | Estado | Hallazgo Clave |
| :-: | :--- | :--- | :--- | :---: | :--- |
| 01 | `spec_xsens_awinda_xda_driver` | `01_orch_hardware_hal` | `backend/hal/xsens_awinda_driver.py`, `backend/hal/xda_bridge_worker.py`, `backend/scripts/setup_xda_sdk.py`, `backend/config/xda_paths.json`, `backend/config/awinda_radio.json`, `backend/xda_sdk/examples/Example_mtw.cs` | **CRÍTICO** | Bloqueo en Modo Config (`gotoMeasurement()` falla tras 32+ llamadas `setOutputConfiguration` indebidas y nunca reintenta); descarte silencioso de `"debug"`; método inexistente `isAwindaStation()` y `openPort(name, baud)` roto en modo XDA en proceso. |
| 02 | `spec_serial_udp_multi_brand_driver` | `01_orch_hardware_hal` | `backend/hal/serial_udp_driver.py` | **ADVERTENCIA** | Colisión del detector WitMotion (`0x55` = ASCII `'U'`, traga líneas JSON/CSV con `'U'`); falta `write_timeout=0.2`; `stop()` hace `join()` antes de `close()`; `port=""` puede abrir `COM6` (Xsens). |
| 03 | `spec_ble_imu_scanner` | `01_orch_hardware_hal` | `backend/hal/ble_driver.py` | **ADVERTENCIA** | Solo soporta UUIDs Movella DOT (sin fallback GATT genérico); sin `disconnected_callback` para limpiar clientes muertos; conexiones secuenciales bloqueantes (6 s c/u); sin botón de desconexión en UI. |
| 04 | `spec_17sensor_synthetic_simulator` | `01_orch_hardware_hal` | `backend/hal/synthetic_simulator.py`, `backend/config/default_awinda_17.json` | **OK** | Emite los 17 IDs exactos de Awinda a 60–120 Hz con poses biomecánicas, correas desalineadas, deriva magnética y agitación controlada (`shake`). |
| 05 | `spec_connection_watchdog_reconnector` | `01_orch_hardware_hal` | `backend/hal/watchdog.py`, `backend/engine.py` | **CRÍTICO** | `self._sensors` se muta en hilos de hardware (`ingest()`) y se itera sin `threading.Lock` en el bucle `asyncio` (`get_active_snapshot()`, `get_diagnostics()`), causando riesgo de `RuntimeError: dictionary changed size during iteration`; `dropped_frames` se infla por tick de 120 Hz. |
| 06 | `spec_dynamic_sensor_mapper` | `01_orch_hardware_hal` | `backend/hal/sensor_mapper.py`, `backend/config/default_awinda_17.json` | **ADVERTENCIA** | Diccionarios `segment_to_sensor`/`sensor_to_segment` accedidos/mutados entre hilos HAL y endpoints REST sin `threading.Lock`; otros trajes Awinda con IDs distintos quedan 100 % en `UNASSIGNED` sin auto-asignación guiada. |
| 07 | `spec_anthropometric_scaler` | `02_orch_kinematics_calibration` | `backend/kinematics/anthropometry.py` | **OK** | Fórmulas de Winter consistentes en metros, árbol de 17+ segmentos con soporte a segmentos custom y orden topológico BFS desde `PELVIS`. |
| 08 | `spec_tpose_static_calibrator` | `02_orch_kinematics_calibration` | `backend/kinematics/calibration.py`, `backend/engine.py` | **ADVERTENCIA** | Promedio de Markley, tolerancias MTw realistas (±6°, <0.35 rad/s) y exigencia de paquetes vivos están bien implementados, pero `start_static()` borra de inmediato `q_offset_final` previo (si el reintento falla, se pierde la calibración anterior). |
| 09 | `spec_dynamic_walk_calibrator` | `02_orch_kinematics_calibration` | `backend/kinematics/calibration.py` | **CRÍTICO** | Ambigüedad de signo ±180° en PCA (`if u[0] < 0: u = -u` y `if v[1] < 0: v = -v`, líneas 453–455 y 482–484): si el sujeto camina o sufre deriva con `|psi| > 90°`, invierte 180° las extremidades o el tronco. |
| 10 | `spec_hierarchical_fk_solver` | `02_orch_kinematics_calibration` | `backend/kinematics/fk_solver.py`, `backend/kinematics/quaternions.py` | **OK** | Propagación FK a 120 Hz en Hamilton `[w,x,y,z]`, herencia de rotación padre en trajes parciales y contacto con el suelo `Y >= 0` validados; mejora menor: filtro de velocidad en cambio de apoyo `free_walk`. |
| 11 | `spec_joint_angle_biomechanics` | `02_orch_kinematics_calibration` | `backend/kinematics/biomechanics.py`, `backend/kinematics/quaternions.py` | **CRÍTICO** | Bug de eje duplicado en codos (`elbow_l`/`elbow_r`, líneas 50–56): tanto `flexion` como `rotation` asignan exactamente `side * y_deg`, impidiendo medir pronosupinación real y mostrando valores idénticos; además `q_to_euler_xyz` sufre gimbal lock cerca de `y = ±90°`. |
| 12 | `spec_sensor_fusion_filter` | `02_orch_kinematics_calibration` | `backend/kinematics/sensor_fusion.py` | **ADVERTENCIA** | `MadgwickFilter` (6/9-DOF Y-up) converge correctamente, pero `MahonyFilter` es solo 6-DOF (ignora magnetómetro) y nunca está expuesto ni seleccionable desde API/UI. |
| 13 | `spec_desktop_shell_architect` | `03_orch_studio_3d_ui` | `frontend/electron/main.cjs`, `frontend/electron/preload.cjs`, `INICIAR_ESTUDIO.bat` | **CRÍTICO** | `spawn(..., { stdio: ['ignore', 'pipe', 'pipe'] })` (líneas 55 y 67) **sin drenar `stdout`/`stderr`** llena el buffer de pipe en Windows (4–64 KB de logs Uvicorn) y **cuelga el backend**; además tiene bucle infinito de reinicio sin tope y pausa muda de 20 s si falta el `.exe`. |
| 14 | `spec_threejs_mannequin_renderer` | `03_orch_studio_3d_ui` | `frontend/src/components/Viewport3D.tsx`, `frontend/src/components/MannequinScene.tsx` | **ADVERTENCIA** | Conversión Hamilton `[w,x,y,z]` → `THREE.Quaternion(x,y,z,w)` correcta y renderizado sin re-renders React vía `liveFrameRef`; pero `capsuleGeometry` (altura base `0.55 + 2r`) escalada por `len` acorta las extremidades ~35 %, las mallas no reflejan torsión axial y `CameraRig` aloca `new THREE.Vector3` en cada frame de `useFrame`. |
| 15 | `spec_dockable_studio_panels` | `03_orch_studio_3d_ui` | `frontend/src/App.tsx`, `TopBar.tsx`, `LeftHardwarePanel.tsx`, `RightBiomechanicsPanel.tsx`, `useStudioStore.ts`, `useMocapStream.ts` | **ADVERTENCIA** | Contradicción visual entre `TopBar` (`16/17 Listos`) y `LeftHardwarePanel` (`0/17 activos`); clic en badge Paso 1 reconecta y corta una sesión activa; `rfChannel` no sincroniza con backend; `YAxis [-120, 120]` recorta flexión de hombro/rodilla. |
| 16 | `spec_calibration_wizard_ui` | `03_orch_studio_3d_ui` | `frontend/src/components/CalibrationWizardModal.tsx` | **OK** | Flujo guiado de 2 etapas con `transition_seq`, cuentas regresivas sincronizadas, alerta explícita de 0 paquetes y modo rápido Solo T-Pose; textos en español fijo (sin `i18n`). |
| 17 | `spec_anthropometric_profile_manager` | `03_orch_studio_3d_ui` | `frontend/src/components/ProfileManagerModal.tsx`, `LeftHardwarePanel.tsx`, `backend/kinematics/anthropometry.py` | **ADVERTENCIA** | Aplicar estatura rápida en Modo Simple (`LeftHardwarePanel.tsx:168-173`) llama `upsertProfile` sin enviar las medidas opcionales existentes, **sobrescribiendo con `null` la envergadura, altura de cadera/rodilla/tobillo, hombros y pie** del perfil activo. |
| 18 | `spec_take_recorder_timeline` | `03_orch_studio_3d_ui` | `backend/recording/recorder.py`, `frontend/src/components/TimelineBar.tsx`, `backend/main.py` | **ADVERTENCIA** | `list_takes()` descomprime y parsea **todos los frames** de cada `.omocap` solo para leer duración/conteo; `load_take()` no sanitiza `take_id` contra path traversal; `export_bvh()` ignora `recorder.skeleton_snapshot` y exporta con el perfil activo actual. |
| 19 | `spec_bvh_exporter` | `04_orch_export_packaging` | `backend/export/bvh_exporter.py`, `backend/engine.py` | **ADVERTENCIA** | Jerarquía de 17 huesos, 54 canales y Euler ZXY continuo válidos, pero escribe altura pélvica tanto en `ROOT OFFSET` (línea 39) como en `MOTION` absoluto (líneas 111–112), duplicando la altura en visores que suman `OFFSET + channel`; `file_name` en `engine.py:342` no se sanitiza con `Path(...).name`. |
| 20 | `spec_blender_fbx_bridge` | `04_orch_export_packaging` | `backend/export/blender_bridge.py`, `blender_tools/convertir_a_fbx.py`, `frontend/src/components/ExportModal.tsx`, `backend/main.py` | **ADVERTENCIA** | `export_fbx_endpoint` ejecuta `subprocess.run(timeout=120)` en el event loop `async` congelando el WebSocket; `ExportModal` omite `scale` en FBX; `convertir_a_fbx.py` importa con `axis_forward="Z"` y exporta con `axis_forward="-Z"` (gira 180°); nunca probado con Blender instalado en este equipo. |
| 21 | `spec_viewport_video_recorder` | `04_orch_export_packaging` | `frontend/src/hooks/useVideoRecorder.ts`, `backend/export/video_converter.py`, `backend/main.py` | **ADVERTENCIA** | `video_convert_mp4` (`main.py:503`) bloquea el event loop `async` hasta 120 s durante `ffmpeg`; `useVideoRecorder.ts:50` hardcodea `Rodilla Izq` en el HUD y no cancela `requestAnimationFrame` al desmontar. |
| 22 | `spec_bilingual_i18n_ux` | `04_orch_export_packaging` | `frontend/src/i18n/es.ts`, `frontend/src/i18n/en.ts`, todos los componentes `.tsx` | **ADVERTENCIA** | Español por defecto bien redactado, pero >50 % de la interfaz (todo Modo Simple, `CalibrationWizardModal`, `ExportModal`, `ProfileManagerModal`, `Viewport3D`, `TimelineBar`) tiene cadenas hardcodeadas que ignoran el cambio a inglés, y falta selector ES/EN en Modo Simple. |
| 23 | `spec_desktop_packager_builder` | `04_orch_export_packaging` | `build/openmocap_backend.spec`, `frontend/package.json`, `backend/paths.py`, `GENERAR_INSTALADOR.bat`, `dist/`, `dist_installer/` | **CRÍTICO** | El instalador `.exe` (166 MB) compila con Python 3.12 **sin XDA**, **sin las 7 DLLs de `dll64/`**, **sin `xda_bridge_worker.py` ni runtime Python 3.10**, incluye `xda_paths.json` con rutas `C:\APLICACION_TRAJE\...`, intenta escribir en `Program Files`, carece de drivers USB Xsens/FTDI, VC++ Redist, icono `.ico` y firma digital, y está desactualizado. |
| 24 | `spec_end_to_end_qa_auditor` | `04_orch_export_packaging` | `tests/verify_pipeline.py` | **ADVERTENCIA** | Valida bien matemáticas, parsers, WebSocket >=60 Hz, calibración MTw parcial y BVH; pero **no** cubre `xda_bridge_worker.py`, **no** audita el `.exe` congelado ni Blender real, **no** detecta bugs de codos/PCA >90°, y su línea 197 llama `/api/hardware/awinda/scan` pudiendo abrir `COM6` en vivo durante los tests. |

---

## 3. ERRORES CRÍTICOS (BLOQUEANTES)

### CRÍTICO #1 — Bloqueo de Awinda (`01210CE2` en `COM6`) en Modo Config (LED sólido, 0 paquetes) tras detectar 16/17 MTw
- **Archivo**: [`backend/hal/xda_bridge_worker.py`](file:///c:/APLICACION_TRAJE/backend/hal/xda_bridge_worker.py#L460-L511) (líneas **233–254, 438–445, 460–511, 598–699**)
- **Código problemático**:
```python
# Líneas 460-509: setOutputConfiguration indebido y duplicado 2x por sensor + requestBatteryLevel bloqueante
def _ensure_children_configured_and_subscribed(output_cfg: Any | None) -> None:
    cand_devs: list[Any] = []
    ...
    with shared_lock:
        cand_devs.extend(list(connectivity_devices.values()))  # <-- SIN deduplicar con master.children()!

    for mtw_dev in cand_devs:
        ...
        if output_cfg is not None and hasattr(mtw_dev, "setOutputConfiguration"):
            mtw_dev.setOutputConfiguration(output_cfg)  # <-- Se ejecuta 2 veces por cada MTw (32-34 llamadas RF!)
        if sid not in attached_children and hasattr(mtw_dev, "requestBatteryLevel"):
            mtw_dev.requestBatteryLevel()               # <-- Otras 16-17 transacciones RF bloqueantes

# Líneas 635-699: gotoMeasurement() falla tras saturar RF y el worker queda atrapado en Config Mode para siempre
output_cfg = _build_output_config(target_rate)
master.setOutputConfiguration(output_cfg)               # <-- Devuelve False en Awinda2 Master y altera estado
_ensure_children_configured_and_subscribed(output_cfg)

meas_ok = False
for _attempt in range(3):
    meas_ok = bool(master.gotoMeasurement())            # <-- 3 intentos rápidos (0.4 s) sin waitForAllDevicesInitialized()
    if meas_ok:
        break
    stop_event.wait(0.4)
...
while not stop_event.is_set():                          # <-- Si meas_ok == False, NUNCA vuelve a intentar gotoMeasurement()
    if (now_mono - last_meta_refresh) >= 0.5:
        _ensure_children_configured_and_subscribed(None)
```
- **Explicación técnica**:
  - Comparado con [`backend/xda_sdk/examples/Example_mtw.cs`](file:///c:/APLICACION_TRAJE/backend/xda_sdk/examples/Example_mtw.cs#L110-L162), el flujo oficial de Movella para Awinda2/MTw2 es estrictamente: `openPort(portInfo)` → `gotoConfig()` → `setUpdateRate(60)` → `enableRadio(ch)` → esperar unión de MTw + `waitForAllDevicesInitialized()` → `master.gotoMeasurement()` → adjuntar callback `onLiveDataAvailable` a cada `control.device(childId)` (y/o `master`). **Nunca** se debe llamar `setOutputConfiguration()` sobre la estación Awinda ni sobre los MTw (además `_build_output_config` en líneas 438–445 ni siquiera incluye `XDI_RateOfTurn`, lo que dejaría el giroscopio en cero).
  - Por culpa de la falta de deduplicación en `cand_devs` y los 16–17 `requestBatteryLevel()`, el enlace RF se satura justo antes de `gotoMeasurement()`. Al fallar `gotoMeasurement()` (`meas_ok = False`), el worker no reintenta ni reporta fallo, dejando el LED fijo en Modo Config y emitiendo `0` líneas `"type": "packets"` indefinidamente.
  - Adicionalmente, en líneas 236–238, `connectivity_devices[sid] = dev` guarda punteros SWIG temporales que nunca se eliminan al desconectarse el sensor, y adjuntar el callback dual (`onLiveDataAvailable` + `onAllDataAvailable`) al maestro y a cada hijo cuadruplica la carga de callbacks SWIG/GIL.

---

### CRÍTICO #2 — Empaquetado `.EXE` inoperante para hardware Xsens en equipos de terceros + escritura en `Program Files`
- **Archivos**:
  - [`build/openmocap_backend.spec`](file:///c:/APLICACION_TRAJE/build/openmocap_backend.spec#L7-L33) (líneas **7–33**)
  - [`backend/config/xda_paths.json`](file:///c:/APLICACION_TRAJE/backend/config/xda_paths.json#L4-L13) (líneas **4–13**)
  - [`backend/hal/xsens_awinda_driver.py`](file:///c:/APLICACION_TRAJE/backend/hal/xsens_awinda_driver.py#L1106-L1135) (líneas **1106–1135**)
  - [`backend/paths.py`](file:///c:/APLICACION_TRAJE/backend/paths.py#L39-L46) (líneas **39–46**)
- **Código problemático**:
```python
# build/openmocap_backend.spec:7-11 (compilado con Python 3.12 en dist/backend/_internal/python312.dll)
datas = [
    (str(ROOT / "backend" / "config"), "backend/config"),  # <-- Empaqueta xda_paths.json con C:\APLICACION_TRAJE\...
    (str(ROOT / "blender_tools"), "blender_tools"),
]
# <-- NO incluye xsensdeviceapi, NO incluye backend/xda_sdk/dll64 (7 DLLs), NO incluye xda_bridge_worker.py ni Python 3.10!

# backend/hal/xsens_awinda_driver.py:1107-1110
py_exe = self._xda_bridge_python
worker_script = Path(__file__).resolve().parent / "xda_bridge_worker.py"  # <-- En PyInstaller frozen NO existe como .py en disco!
if py_exe is None or not py_exe.is_file() or not worker_script.is_file():
    return False

# backend/paths.py:39-46
def get_config_dir() -> Path:
    res_cfg = get_resource_root() / "backend" / "config"   # <-- En frozen apunta a C:\Program Files\...\backend\_internal\backend\config (SOLO LECTURA)
    if res_cfg.exists():
        return res_cfg
```
- **Explicación técnica**:
  - Se inspeccionó `dist/backend/` y `dist_installer/OpenMocap Studio Setup 1.0.0.exe` (`166 MB`, compilado el `21/11/26 10:22 a.m.`): usa `python312.dll`, no contiene `xsensdeviceapi` ni las 7 DLLs nativas requeridas (`xsensdeviceapi64.dll`, `xstypes64.dll`, `xkf3hm_filter64.dll`, `xkf3i_filter64.dll`, `xkf700_filter64.dll`, `xkfcore_filter64.dll`, `libiomp5md.dll`), ni el puente Python 3.10.
  - En cualquier otra PC, `worker_script.is_file()` y `py_exe.is_file()` serán siempre `False`, deshabilitando el motor oficial XDA al 100 %. Además, al instalarse en `C:\Program Files\OpenMocap Studio`, intentar escribir `awinda_radio.json` o `xda_paths.json` en `get_config_dir()` fallará por permisos de Windows (`PermissionError`).

---

### CRÍTICO #3 — Deadlock de Pipe `stdout`/`stderr` en Electron que congela el backend Python en Windows
- **Archivo**: [`frontend/electron/main.cjs`](file:///c:/APLICACION_TRAJE/frontend/electron/main.cjs#L48-L84) (líneas **48–84**)
- **Código problemático**:
```javascript
// Líneas 52-69
backendProcess = spawn(backendExe, ['--host', BACKEND_HOST, '--port', String(BACKEND_PORT)], {
  cwd: path.dirname(backendExe),
  windowsHide: true,
  stdio: ['ignore', 'pipe', 'pipe'],  // <-- Crea pipes stdout/stderr SIN ningún listener .on('data') ni .resume()!
});
...
backendProcess.on('exit', () => {
  backendProcess = null;
  if (!isQuitting) {
    setTimeout(() => { startBackendIfNeeded().catch(() => {}); }, 1500); // <-- Bucle infinito sin tope de reintentos
  }
});
```
- **Explicación técnica**:
  - [`backend/main.py:547`](file:///c:/APLICACION_TRAJE/backend/main.py#L547) ejecuta `uvicorn.run(app, ..., log_level="info")`, imprimiendo cada petición REST y log en `stdout`/`stderr`. En Windows, un pipe sin lector en Node.js se llena tras 4–64 KB, tras lo cual el siguiente `write()` de Python/Uvicorn **bloquea el hilo principal del servidor FastAPI indefinidamente**, congelando el WebSocket y toda la aplicación.

---

### CRÍTICO #4 — Condición de Carrera (`RuntimeError`) sin `threading.Lock` en `ConnectionWatchdog` y `SensorMapper`
- **Archivos**:
  - [`backend/hal/watchdog.py`](file:///c:/APLICACION_TRAJE/backend/hal/watchdog.py#L35-L149) (líneas **35, 51, 89, 131**)
  - [`backend/hal/sensor_mapper.py`](file:///c:/APLICACION_TRAJE/backend/hal/sensor_mapper.py#L35-L149) (líneas **35–149**)
- **Código problemático**:
```python
# backend/hal/watchdog.py:51 (ejecutado en hilos de hardware: XsensBridgeStdout / SerialIMULoop / Simulator)
self._sensors[packet.sensor_id] = state

# backend/hal/watchdog.py:89 y 131 (ejecutado a 120 Hz en el hilo principal asyncio vía engine.step_once())
for sid, state in self._sensors.items():   # <-- Sin threading.Lock!
```
- **Explicación técnica**:
  - Mientras los 17 sensores MTw se van conectando secuencialmente en el hilo `XsensBridgeStdout`, `ingest()` inserta nuevas claves en `self._sensors` simultáneamente mientras `step_once()` itera `self._sensors.items()` 120 veces por segundo (dos veces por ciclo: `get_active_snapshot()` y `get_diagnostics()`). Esto provoca excepciones intermitentes `RuntimeError: dictionary changed size during iteration` que abortan el bucle `_main_loop()` del motor. El mismo patrón sin lock ocurre en `SensorMapper` (`resolve_and_check_shake` vs endpoints `assign`/`reset`).

---

### CRÍTICO #5 — Inversión de 180° en Calibración Dinámica de Caminata cuando `|psi| > 90°`
- **Archivo**: [`backend/kinematics/calibration.py`](file:///c:/APLICACION_TRAJE/backend/kinematics/calibration.py#L429-L486) (líneas **452–455 y 481–484**)
- **Código problemático**:
```python
# _estimate_limb_yaw_from_gyro (líneas 452-455)
u = eigvecs[:, 1]
if float(u[0]) < 0.0:   # <-- Fuerza u_x >= 0, asumiendo que |psi| < 90° respecto al Norte/Este magnético!
    u = -u
psi = math.atan2(-float(u[1]), float(u[0]))

# _estimate_axial_yaw_from_accel (líneas 481-484)
v = eigvecs[:, 1]
if float(v[1]) < 0.0:   # <-- Fuerza v_z >= 0, asumiendo caminata dentro de +-90° del eje +Z magnético!
    v = -v
psi = math.atan2(float(v[0]), float(v[1]))
```
- **Explicación técnica**:
  - Los autovectores PCA tienen ambigüedad de signo (`±u`). Forzar `u[0] >= 0` y `v[1] >= 0` restringe matemáticamente el ángulo `psi` al rango `(-90°, +90°)`. En una sala real, el sujeto puede estar mirando al Sur o tener una perturbación ferromagnética >90° respecto al rumbo inicial: en ese caso `psi` se envuelve 180°, volteando al revés las piernas, brazos o torso tras finalizar los 6 segundos de caminata. La desambiguación debe alinearse con la referencia de rumbo de la fase estática (o con la dirección media real de la postura estática de cada segmento), no con el eje global fijo `+X`/`+Z`.

---

### CRÍTICO #6 — Bug de Eje Duplicado en Biomecánica de Codos (`flexion == rotation`)
- **Archivo**: [`backend/kinematics/biomechanics.py`](file:///c:/APLICACION_TRAJE/backend/kinematics/biomechanics.py#L42-L62) (líneas **42–57**)
- **Código problemático**:
```python
x_deg, y_deg, z_deg = q_to_euler_xyz(q_rel)
...
elif joint_key in ("elbow_l", "elbow_r"):
    flexion = side * y_deg     # <-- Usa y_deg para flexión de codo
else:
    flexion = -x_deg

abduction = side * z_deg
rotation = side * y_deg        # <-- Sobrescribe/repite exactamente side * y_deg para rotación!
```
- **Explicación técnica**:
  - En T-Pose los brazos se extienden a lo largo del eje medio-lateral `±X`, por lo que la flexión horizontal del codo gira alrededor de `Y` (`±y_deg`), mientras que la pronosupinación axial del antebrazo gira alrededor de `X` (`±x_deg`). Como la línea 56 asigna siempre `rotation = side * y_deg`, `elbow_l` y `elbow_r` reportan números idénticos en Flexión y Rotación Interna/Externa. Además, `q_to_euler_xyz` entra en singularidad (gimbal lock) cuando `y ≈ ±90°` (brazos bajados o elevados).

---

### CRÍTICO #7 — Ocultamiento de errores `"debug"`, acumulación fantasma de sensores y fallos en modo XDA en proceso (`xsens_awinda_driver.py`)
- **Archivo**: [`backend/hal/xsens_awinda_driver.py`](file:///c:/APLICACION_TRAJE/backend/hal/xsens_awinda_driver.py#L821-L1206) (líneas **821, 983–1093, 1194, 1202**)
- **Código problemático**:
```python
# Líneas 821 y 1194: método INEXISTENTE en xsensdeviceapi 2022.2 SWIG
if p.deviceId().isWirelessMaster() or p.deviceId().isAwindaStation() or p.deviceId().isAwinda2Station():

# Línea 1202: firma que falla en Awinda2 Dongle (debe ser control.openPort(target_port))
if not control.openPort(target_port.portName(), target_port.baudrate()):

# Líneas 1027-1032: _seen_mtws solo crece, nunca refleja sensores desconectados; y mtype == "debug" se ignora por completo
if "detected_mtws" in msg and isinstance(msg["detected_mtws"], list):
    for raw_sid in msg["detected_mtws"]:
        self._seen_mtws.add(norm_sid)
    self.detected_mtws = sorted(self._seen_mtws)
```
- **Explicación técnica**:
  - `xsensdeviceapi` 2022.2 no define `isAwindaStation()` (solo `isAwinda2()`, `isAwinda2Station()`, `isAwindaX()`, `isWirelessMaster()`), lo que dispara `AttributeError` en `scan_stations()` y `_start_xda_mode()`.
  - El puente ignora los mensajes `"type": "debug"` emitidos por `_debug_once()` en `xda_bridge_worker.py`, dejando al operador ciego ante excepciones de SWIG/callbacks en vivo.
  - Al no reemplazar `self.detected_mtws` con la lista actual del worker, si un sensor se apaga sigue apareciendo como conectado.

---

## 4. ERRORES MODERADOS Y MEJORAS DE UX/ESTABILIDAD

### Backend (HAL, Cinemática, Grabación y API)
1. **Colisión ASCII `'U'` (`0x55`) en parser WitMotion** ([`backend/hal/serial_udp_driver.py:335`](file:///c:/APLICACION_TRAJE/backend/hal/serial_udp_driver.py#L335)): `if b"\x55" in chunk and (chunk[0] == 0x55 or b"\x55\x59" in chunk or b"\x55\x51" in chunk): ... continue` confunde el byte `0x55` con la letra ASCII `'U'` (por ejemplo paquetes JSON/CSV que empiecen con `U` o contengan `"UQ"`/`"UY"`), tragándose silenciosamente tramas de texto ESP32/Arduino. Además faltan `write_timeout=0.2` ([líneas 280 y 310](file:///c:/APLICACION_TRAJE/backend/hal/serial_udp_driver.py#L280)), `stop()` hace `join()` antes de `close()` ([líneas 357–364](file:///c:/APLICACION_TRAJE/backend/hal/serial_udp_driver.py#L357-L364)), y `port=""` ([línea 306](file:///c:/APLICACION_TRAJE/backend/hal/serial_udp_driver.py#L306)) puede capturar `COM6` (Xsens `VID 0x2639`).
2. **Bloqueo del Event Loop `async` al exportar FBX o convertir Video MP4** ([`backend/main.py:480-503`](file:///c:/APLICACION_TRAJE/backend/main.py#L480-L503)): `export_fbx_endpoint` y `video_convert_mp4` invocan `subprocess.run(..., timeout=120)` síncronamente dentro de `async def` sin `await asyncio.to_thread(...)`, congelando el streaming WebSocket hasta por 2 minutos.
3. **Doble desplazamiento vertical en exportación BVH y falta de sanitización de rutas** ([`backend/export/bvh_exporter.py:39,111-112`](file:///c:/APLICACION_TRAJE/backend/export/bvh_exporter.py#L39), [`backend/engine.py:342-346`](file:///c:/APLICACION_TRAJE/backend/engine.py#L342-L346)):
   - `ROOT OFFSET` escribe la altura de pelvis (`~0.93 m`) y `MOTION` escribe también la posición mundial absoluta (`~0.93 m`); motores que suman `OFFSET + channel` duplican la altura del personaje (`1.86 m`). El estándar BVH limpio usa `ROOT OFFSET 0.000000 0.000000 0.000000` cuando `MOTION` lleva coordenadas absolutas.
   - `engine.export_bvh()` usa `self.skeleton` (perfil activo actual) en lugar de `self.recorder.skeleton_snapshot` (perfil con el que se grabó la toma cargada) y no sanitiza `file_name` con `Path(base).name`.
4. **Inversión de 180° en el puente Blender FBX y falta de parámetro `scale`** ([`blender_tools/convertir_a_fbx.py:103,138`](file:///c:/APLICACION_TRAJE/blender_tools/convertir_a_fbx.py#L103), [`frontend/src/components/ExportModal.tsx:81-86`](file:///c:/APLICACION_TRAJE/frontend/src/components/ExportModal.tsx#L81-L86)): importa BVH con `axis_forward="Z"` y exporta FBX con `axis_forward="-Z"`, rotando 180° la orientación del personaje; además `handleExportFbx` ignora el selector `scale` (1.0 vs 100.0).
5. **Rendimiento y seguridad en `TakeRecorder`** ([`backend/recording/recorder.py:142-168`](file:///c:/APLICACION_TRAJE/backend/recording/recorder.py#L142-L168)): `list_takes()` descomprime y parsea **el JSON completo con todos los frames** de cada `.omocap` solo para mostrar la lista de tomas; `load_take(take_id)` no sanitiza `Path(take_id).name`.
6. **Conteo inflado de `dropped_frames` y estado muerto en `engine.py`** ([`backend/hal/watchdog.py:105`](file:///c:/APLICACION_TRAJE/backend/hal/watchdog.py#L105), [`backend/engine.py:138`](file:///c:/APLICACION_TRAJE/backend/engine.py#L138)): `dropped_frames` suma 1 cada tick de 120 Hz durante interpolación en vez de contar paquetes reales perdidos; `self._latest_packets` se llena sin leerse ni limpiarse nunca.
7. **Pérdida de calibración previa si falla un reintento** ([`backend/kinematics/calibration.py:208-211`](file:///c:/APLICACION_TRAJE/backend/kinematics/calibration.py#L208-L211)): `start_static()` vacía `q_offset_final` antes de saber si la nueva captura tendrá éxito.
8. **Bluetooth BLE incompleto** ([`backend/hal/ble_driver.py:70-150`](file:///c:/APLICACION_TRAJE/backend/hal/ble_driver.py#L70-L150)): carece de servicio GATT genérico de cuaterniones, no maneja `disconnected_callback` y bloquea el arranque con conexiones secuenciales de 6 s.
9. **Interferencia de `tests/verify_pipeline.py` con hardware real** ([`tests/verify_pipeline.py:197`](file:///c:/APLICACION_TRAJE/tests/verify_pipeline.py#L197)): llama `POST /api/hardware/awinda/scan` (`auto_connect=True`), lo cual puede abrir `COM6` y lanzar el worker XDA en mitad de una prueba automatizada.

### Frontend, UX y Visor 3D
10. **Contradicción visual de sensores en pantalla** ([`TopBar.tsx:98`](file:///c:/APLICACION_TRAJE/frontend/src/components/TopBar.tsx#L98) vs [`LeftHardwarePanel.tsx:257,359`](file:///c:/APLICACION_TRAJE/frontend/src/components/LeftHardwarePanel.tsx#L257)): la barra superior muestra `awinda.connected_sensor_count` (`16/17 Sensores Listos`), mientras la tarjeta de antena y la silueta corporal muestran `onlineCount` del watchdog (`0/17 activos`). Deben distinguir explícitamente **"Vinculados en radio (16/17)"** vs **"Enviando datos (0/17)"**.
11. **Pérdida silenciosa de medidas antropométricas opcionales en Modo Simple** ([`LeftHardwarePanel.tsx:167-173`](file:///c:/APLICACION_TRAJE/frontend/src/components/LeftHardwarePanel.tsx#L167-L173)): `handleApplyQuickHeight` envía solo `{ id, name, height_cm, activate: true }` a `/api/profiles`, lo que provoca que el backend reemplace con `None` las medidas opcionales (`arm_span_cm`, `hip_height_cm`, `knee_height_cm`, `ankle_height_cm`, `shoulder_width_cm`, `foot_length_cm`) del perfil activo.
12. **Reconexión accidental en un clic** ([`TopBar.tsx:165-167`](file:///c:/APLICACION_TRAJE/frontend/src/components/TopBar.tsx#L165-L167)): hacer clic en la insignia verde `"1. Antena Encendida"` reinicia inmediatamente la antena (`api.reconnectAwinda()`), cortando una captura en curso sin confirmación.
13. **Proporciones visuales y GC del maniquí 3D** ([`MannequinScene.tsx:64,180-185,304`](file:///c:/APLICACION_TRAJE/frontend/src/components/MannequinScene.tsx#L180-L185)): `<capsuleGeometry args={[rad * 0.72, 0.55, 8, 16]} />` tiene altura intrínseca `0.55 + 2r` (~0.64 m) y al escalarse por `len` queda ~35 % más corta que el hueso real; las extremidades solo alinean el eje (`tempBoneQuat`) sin mostrar torsión axial; y `CameraRig` instancia `new THREE.Vector3(...)` en cada fotograma (`60 veces/s`) cuando `followPelvis` está activo.
14. **Gráfica biomecánica recortada y falta de botón desconectar BLE** ([`RightBiomechanicsPanel.tsx:99`](file:///c:/APLICACION_TRAJE/frontend/src/components/RightBiomechanicsPanel.tsx#L99), [`LeftHardwarePanel.tsx:63,729-738`](file:///c:/APLICACION_TRAJE/frontend/src/components/LeftHardwarePanel.tsx#L729-L738)): `YAxis domain={[-120, 120]}` recorta movimientos >120° (hombro hasta 180°, rodilla hasta 145°); `rfChannel` inicia fijo en `11` sin reflejar el canal activo real; y BLE no tiene botón para detener el driver.
15. **Localización bilingüe ES/EN incompleta** ([`TopBar.tsx`](file:///c:/APLICACION_TRAJE/frontend/src/components/TopBar.tsx#L158-L237), [`Viewport3D.tsx`](file:///c:/APLICACION_TRAJE/frontend/src/components/Viewport3D.tsx#L71-L93), [`TimelineBar.tsx`](file:///c:/APLICACION_TRAJE/frontend/src/components/TimelineBar.tsx#L91-L131), [`CalibrationWizardModal.tsx`](file:///c:/APLICACION_TRAJE/frontend/src/components/CalibrationWizardModal.tsx), [`ExportModal.tsx`](file:///c:/APLICACION_TRAJE/frontend/src/components/ExportModal.tsx), [`ProfileManagerModal.tsx`](file:///c:/APLICACION_TRAJE/frontend/src/components/ProfileManagerModal.tsx)): más del 50 % de etiquetas visibles están escritas directamente en español y no reaccionan al cambiar `locale` a `'en'`.

---

## 5. AUDITORÍA DE EMPAQUETADO `.EXE` (LO QUE FALTA PARA DISTRIBUIR A OTROS USUARIOS)

Estado verificado en disco: existe `dist_installer/OpenMocap Studio Setup 1.0.0.exe` (`165.99 MB`, compilado el `21/11/26 10:22 a.m.`) y `dist/backend/openmocap-backend.exe` (`13.73 MB`). **Este instalador NO está listo para entregarse a otros usuarios** por las siguientes 10 brechas concretas:

| # | Brecha de Empaquetado | Evidencia Verificada | Impacto en otra PC | Qué falta implementar |
| :-: | :--- | :--- | :--- | :--- |
| 1 | **Motor XDA ausente (Python 3.12 vs 3.10)** | `dist/backend/_internal/python312.dll`; `xsensdeviceapi-2022.2.0-cp310-none-win_amd64.whl` es solo `cp310`. | **Bloqueante**: 0 % de soporte XDA en la PC destino; la antena Awinda no vincula MTw. | **Opción recomendada (más limpia)**: compilar un segundo binario `xda-bridge-worker.exe` con PyInstaller desde `backend\.venv_xda` (Python 3.10) e incluirlo junto a `openmocap-backend.exe` en `resources/backend/` — o migrar todo el backend a Python 3.10 para cargar `xsensdeviceapi` en proceso. |
| 2 | **7 DLLs nativas de Movella XDA faltantes** | `backend/xda_sdk/dll64/` (`xsensdeviceapi64.dll`, `xstypes64.dll`, `xkf3hm_filter64.dll`, `xkf3i_filter64.dll`, `xkf700_filter64.dll`, `xkfcore_filter64.dll`, `libiomp5md.dll`, ~70 MB) no está en `openmocap_backend.spec`. | `ImportError` / fallo de filtros Kalman XKF al intentar usar Xsens. | Incluir las 7 DLLs en `binaries` del `.spec` del worker (o backend Python 3.10) y registrarlas con `os.add_dll_directory()` relativo a `sys._MEIPASS` / `Path(sys.executable).parent`. |
| 3 | **`xda_bridge_worker.py` inexistente en modo frozen** | [`xsens_awinda_driver.py:1108`](file:///c:/APLICACION_TRAJE/backend/hal/xsens_awinda_driver.py#L1108) busca `Path(__file__).parent / "xda_bridge_worker.py"`. | En PyInstaller nunca encuentra el worker. | Detectar `getattr(sys, "frozen", False)` y lanzar `Path(sys.executable).parent / "xda-bridge-worker.exe"` (sin depender de `python.exe` externo). |
| 4 | **Rutas absolutas de la PC de desarrollo empaquetadas** | [`backend/config/xda_paths.json:4-12`](file:///c:/APLICACION_TRAJE/backend/config/xda_paths.json#L4-L12) hardcodea `C:\APLICACION_TRAJE\backend\.venv_xda\...` y `awinda_radio.json` lleva `station_id: "01210CE2"`. | El instalador busca rutas inexistentes de tu máquina. | Excluir `xda_paths.json` y `awinda_radio.json` del bundle (o generar plantilla limpia), empaquetando solo `default_awinda_17.json`. |
| 5 | **Escritura en `C:\Program Files` (solo lectura)** | [`backend/paths.py:39-46`](file:///c:/APLICACION_TRAJE/backend/paths.py#L39-L46) devuelve `_internal/backend/config`; `xsens_awinda_driver.py` y `xda_bridge_worker.py` escriben ahí. | `PermissionError` al guardar el canal RF ganador o rutas XDA en instalaciones estándar sin Admin. | Leer configuraciones de fábrica desde `get_config_dir()` (solo lectura) y persistir **toda** escritura (`awinda_radio.json`, `xda_paths.json`, `blender_path.json`, perfiles, tomas) en `ensure_runtime_dirs()["settings"]` (`%LOCALAPPDATA%\OpenMocapStudio\data\settings`). |
| 6 | **Pipe Deadlock en `electron/main.cjs`** | [`frontend/electron/main.cjs:55,67`](file:///c:/APLICACION_TRAJE/frontend/electron/main.cjs#L55) usa `stdio: ['ignore', 'pipe', 'pipe']` sin drenar. | El backend empaquetado se congela tras unos minutos de uso. | Redirigir `stdout`/`stderr` a un archivo rotativo en `%LOCALAPPDATA%\OpenMocapStudio\logs\backend.log` o drenarlos activamente con listeners. |
| 7 | **Drivers USB FTDI/Xsens (`VID 0x2639`) y VC++ Redistributable** | No existe instalador ni script NSIS auxiliar en `build/` ni `frontend/package.json`. | En Windows limpio, al enchufar la antena Awinda no aparece puerto `COMx` y `xsensdeviceapi64.dll` puede fallar por falta de `MSVCP140.dll`. | Incluir el instalador silencioso de driver USB Xsens/FTDI (`dpinst` / `CDM` / paquete oficial Movella USB) y `vc_redist.x64.exe` en un script NSIS `customInstall` (opcional con checkbox en el asistente). |
| 8 | **Sin icono `.ico` ni firma Authenticode** | Búsqueda en todo el repo devolvió 0 archivos `.ico`/`.png`; [`frontend/package.json:70`](file:///c:/APLICACION_TRAJE/frontend/package.json#L70) tiene `"signAndEditExecutable": false`. | Icono genérico de Electron + pantalla azul de Windows SmartScreen ("Windows protegió su PC"). | Crear `build/icon.ico` (`256x256` multi-resolución), configurar `"icon": "../build/icon.ico"` en `package.json`, habilitar `signAndEditExecutable: true` y firmar con certificado Code Signing para distribución pública. |
| 9 | **Instalador `.exe` desactualizado + verificación Blender** | `OpenMocap Studio Setup 1.0.0.exe` es del `21/11/26 10:22 a.m.` (anterior a las correcciones de calibración y XDA); Blender no está instalado en este equipo. | El `.exe` en `dist_installer/` contiene código viejo y el puente FBX nunca se validó en vivo. | Recompilar con [`GENERAR_INSTALADOR.bat`](file:///c:/APLICACION_TRAJE/GENERAR_INSTALADOR.bat) tras aplicar los arreglos (incluyendo compilación del worker Python 3.10) y probar el instalador en una VM/PC limpia + probar conversión BVH→FBX con Blender 4.x real. |
| 10 | **Limpieza de `dist/backend` (`pytest`/`setuptools`/`watchfiles`)** | `dist/backend/_internal/` incluye `setuptools`, `pluggy`, `watchfiles` innecesarios. | Infla innecesariamente el instalador. | Añadir `excludes=["tkinter", "pytest", "pluggy", "watchfiles", "httpx"]` en [`build/openmocap_backend.spec`](file:///c:/APLICACION_TRAJE/build/openmocap_backend.spec). |

---

## 6. PLAN DE CORRECCIÓN EN ORDEN DE PRIORIDAD

### Prioridad P0 — Desbloquear captura física real con el traje Xsens Awinda (COM6)
1. **Reescribir la secuencia XDA en [`backend/hal/xda_bridge_worker.py`](file:///c:/APLICACION_TRAJE/backend/hal/xda_bridge_worker.py) siguiendo fielmente [`Example_mtw.cs`](file:///c:/APLICACION_TRAJE/backend/xda_sdk/examples/Example_mtw.cs)**:
   - Eliminar **por completo** `master.setOutputConfiguration(...)`, `mtw_dev.setOutputConfiguration(...)` y las llamadas masivas a `requestBatteryLevel()` antes de `gotoMeasurement()`.
   - Esperar estabilización de unión de MTw (reiniciar ventana de 2.5 s cada vez que se suma un nuevo sensor, hasta 17 sensores o tope máximo) y llamar a `master.waitForAllDevicesInitialized()` antes de `master.gotoMeasurement()`.
   - Si `master.gotoMeasurement()` devuelve `False`, emitir diagnóstico explícito (`lastResultText()`) y reintentar con backoff limpio (e incluso `gotoConfig()` → `gotoMeasurement()`) en vez de congelarse en `radio_on` para siempre.
   - Usar únicamente `control.device(did)` (nunca cachear punteros SWIG en `connectivity_devices`), limpiar `connected_mtws` en desconexión y registrar **solo** `onLiveDataAvailable` por cada MTw hijo (o `onAllDataAvailable` en el maestro, evitando cuádruple disparo).
   - Leer batería de forma periódica de baja frecuencia (cada 10 s, no en la transición a medición) y comprobar `control.setOptions(xda.XSO_Orientation, xda.XSO_None)` a nivel de `XsControl` si fuera necesario.
2. **Corregir [`backend/hal/xsens_awinda_driver.py`](file:///c:/APLICACION_TRAJE/backend/hal/xsens_awinda_driver.py)**:
   - Procesar y registrar eventos `"type": "debug"` del worker en `last_handshake_log`.
   - Sincronizar `self.detected_mtws` con la lista viva actual (no solo acumular en `_seen_mtws`).
   - Reemplazar `isAwindaStation()` por `isAwinda2()`/`isAwinda2Station()`/`isAwindaX()`/`isWirelessMaster()` y corregir `control.openPort(target_port)`.
3. **Corregir concurrencia en [`backend/hal/watchdog.py`](file:///c:/APLICACION_TRAJE/backend/hal/watchdog.py) y [`backend/hal/sensor_mapper.py`](file:///c:/APLICACION_TRAJE/backend/hal/sensor_mapper.py)**:
   - Proteger todos los accesos a `self._sensors` y a los diccionarios de mapeo con `threading.RLock()`.
   - Contabilizar `dropped_frames` solo por transición real de pérdida/salto, no en cada tick de 120 Hz.
4. **Corregir deadlock de pipe en [`frontend/electron/main.cjs`](file:///c:/APLICACION_TRAJE/frontend/electron/main.cjs)**:
   - Drenar `backendProcess.stdout` y `backendProcess.stderr` hacia archivo de log en `%LOCALAPPDATA%\OpenMocapStudio\logs\backend.log`, añadir tope de reintentos (máx. 3) y notificar a la ventana si el backend no existe.

### Prioridad P1 — Precisión Biomecánica y Confiabilidad de Calibración/UI
5. **Corregir ambigüedad ±180° en PCA de caminata ([`backend/kinematics/calibration.py`](file:///c:/APLICACION_TRAJE/backend/kinematics/calibration.py))**:
   - Desambiguar el signo de los autovectores `u` y `v` usando la proyección del rumbo estático previo (o el signo físico de flexión de rodilla/propulsión en el marco local de postura estática) para soportar caminatas en cualquier dirección `0°–360°`.
   - Preservar `q_offset_final` en un respaldo temporal durante `start_static()` para no destruir una calibración buena si un reintento falla.
6. **Corregir ejes de codo en [`backend/kinematics/biomechanics.py`](file:///c:/APLICACION_TRAJE/backend/kinematics/biomechanics.py)**:
   - Separar flexión de codo (`side * y_deg`) de pronosupinación/rotación axial del antebrazo (`side * x_deg`) usando descomposición libre de gimbal lock para extremidades horizontales (p. ej. Euler `Y-Z-X` para brazos/hombros).
7. **Corregir contradicciones y pérdidas de datos en Frontend**:
   - Mostrar claramente **Vinculados en radio** vs **Activos enviando datos** en [`TopBar.tsx`](file:///c:/APLICACION_TRAJE/frontend/src/components/TopBar.tsx) y [`LeftHardwarePanel.tsx`](file:///c:/APLICACION_TRAJE/frontend/src/components/LeftHardwarePanel.tsx), evitar reconexión accidental al tocar el badge Paso 1 cuando ya está en `streaming`.
   - En `handleApplyQuickHeight` ([`LeftHardwarePanel.tsx:167-173`](file:///c:/APLICACION_TRAJE/frontend/src/components/LeftHardwarePanel.tsx#L167-L173)), preservar las medidas opcionales del `activeProfile` al guardar.
   - Ampliar `YAxis` en [`RightBiomechanicsPanel.tsx:99`](file:///c:/APLICACION_TRAJE/frontend/src/components/RightBiomechanicsPanel.tsx#L99) a `[-180, 180]`, sincronizar `rfChannel` con `awinda?.channel`, y agregar botón de desconexión BLE.

### Prioridad P2 — Exportación, Rendimiento, Multi-Marca y Bilingüismo
8. **Desbloquear el event loop en [`backend/main.py`](file:///c:/APLICACION_TRAJE/backend/main.py)**:
   - Ejecutar `engine.export_fbx(...)`, `engine.export_bvh(...)` y `convert_webm_to_mp4(...)` con `await asyncio.to_thread(...)`.
9. **Corregir BVH, Blender FBX y `TakeRecorder`**:
   - Fijar `ROOT OFFSET 0.000000 0.000000 0.000000` en [`bvh_exporter.py`](file:///c:/APLICACION_TRAJE/backend/export/bvh_exporter.py), usar `self.recorder.skeleton_snapshot` al exportar tomas cargadas, sanitizar `file_name` y `take_id` con `Path(...).name`.
   - Alinear `axis_forward` en [`blender_tools/convertir_a_fbx.py`](file:///c:/APLICACION_TRAJE/blender_tools/convertir_a_fbx.py) y pasar `scale` desde [`ExportModal.tsx`](file:///c:/APLICACION_TRAJE/frontend/src/components/ExportModal.tsx).
   - Almacenar un pequeño archivo índice `.meta.json` junto a cada `.omocap` (o leer encabezado sin cargar `frames`) para acelerar `list_takes()`.
10. **Endurecer drivers multi-marca y visor 3D**:
    - En [`serial_udp_driver.py`](file:///c:/APLICACION_TRAJE/backend/hal/serial_udp_driver.py): exigir validación de checksum WitMotion antes de consumir un chunk (eliminando el falso positivo con `'U'`), añadir `write_timeout=0.2`, cerrar serial antes de `join()`, y excluir puertos `VID 0x2639` al auto-seleccionar `COM`.
    - En [`MannequinScene.tsx`](file:///c:/APLICACION_TRAJE/frontend/src/components/MannequinScene.tsx): corregir altura de cápsulas a longitud real `len`, eliminar `new THREE.Vector3` dentro de `useFrame` y completar la cobertura `i18n` en Modo Simple y modales.

### Prioridad P3 — Empaquetado `.EXE` Distribuible y QA Completo
11. **Construir instalador autocontenido con XDA Python 3.10 + DLLs + rutas escribibles**:
    - Separar configuración de solo lectura (`get_config_dir()`) de configuración persistente de usuario (`ensure_runtime_dirs()["settings"]`) en [`backend/paths.py`](file:///c:/APLICACION_TRAJE/backend/paths.py) y excluir `xda_paths.json`/`awinda_radio.json` del bundle.
    - Crear `build/xda_bridge_worker.spec` compilado con `backend\.venv_xda\Scripts\pyinstaller.exe` (Python 3.10 + `xsensdeviceapi` + las 7 DLLs de `backend/xda_sdk/dll64/`) produciendo `dist/backend/xda-bridge-worker.exe`, y actualizar [`xsens_awinda_driver.py`](file:///c:/APLICACION_TRAJE/backend/hal/xsens_awinda_driver.py) para invocarlo en modo frozen.
    - Añadir `build/icon.ico`, excluir paquetes de desarrollo en `openmocap_backend.spec`, integrar instalador opcional de driver USB Xsens/FTDI + VC++ Redistributable en NSIS y actualizar [`GENERAR_INSTALADOR.bat`](file:///c:/APLICACION_TRAJE/GENERAR_INSTALADOR.bat).
12. **Blindar [`tests/verify_pipeline.py`](file:///c:/APLICACION_TRAJE/tests/verify_pipeline.py)**:
    - Añadir pruebas unitarias para: `xda_bridge_worker.py` (con mocks SWIG), calibración PCA con `psi = 135°` y `-150°`, ángulos independientes de flexión vs rotación de codo, protección contra path traversal y flag `--no-hardware` para que jamás abra `COM6` al correr CI/QA.
