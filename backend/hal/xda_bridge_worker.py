"""
Puente oficial Xsens Device API (XDA) ejecutado sobre Python 3.10 (.venv_xda o binario congelado).

Implementa el flujo oficial de Movella/Xsens MT SDK (`Example_mtw.cs`) para estaciones Awinda2/MTw:
  - Carga de DLLs mediante os.add_dll_directory() (tanto desarrollo como PyInstaller --onefile).
  - XsControl_construct() -> XsScanner_scanPorts() -> openPort(XsPortInfo).
  - gotoConfig() -> setUpdateRate(60) -> barrido automático enableRadio(ch) en Modo Config
    sin llamar setOutputConfiguration() ni requestBatteryLevel() masivos sobre la estación o hijos.
  - Estabilización real de unión MTw (ventana reiniciable 2.5 s hasta 17 sensores o tope 12 s)
    seguida de master.waitForAllDevicesInitialized().
  - Transición robusta master.gotoMeasurement() con hasta 5 reintentos y recuperación gotoConfig().
  - Callbacks SWIG ligeros e independientes: conectividad en maestro y onLiveDataAvailable por hijo.
  - Lectura periódica de batería en baja prioridad (cada 10 s).
"""

from __future__ import annotations

import argparse
import importlib
import json
import math
import os
import signal
import sys
import threading
import time
from pathlib import Path
from typing import Any, Callable

# Mantener vivos los handles devueltos por os.add_dll_directory() durante toda la vida del proceso
_DLL_DIR_HANDLES: list[Any] = []

SWEEP_CHANNELS: list[int] = [11, 15, 20, 25, 12, 13, 14, 16, 17, 18, 19, 21, 22, 23, 24]


def _normalize_sensor_id(raw_id: Any) -> str:
    txt = str(raw_id or "").strip().upper()
    if txt.startswith("0X"):
        txt = txt[2:]
    if txt and len(txt) < 8 and all(ch in "0123456789ABCDEF" for ch in txt):
        txt = txt.zfill(8)
    return txt


def _device_id_str(did: Any) -> str:
    if did is None:
        return ""
    try:
        if hasattr(did, "toXsString"):
            return _normalize_sensor_id(did.toXsString())
        return _normalize_sensor_id(str(did))
    except Exception:
        return ""


def _is_master_or_dongle_id(did: Any) -> bool:
    if did is None:
        return False
    for attr in ("isWirelessMaster", "isAwinda2Dongle", "isAwindaXDongle", "isAwinda2Station", "isAwinda2", "isAwindaX"):
        fn = getattr(did, attr, None)
        if callable(fn):
            try:
                if fn():
                    return True
            except Exception:
                pass
    return False


def _build_channel_order(initial_channel: int) -> list[int]:
    ch = max(11, min(25, int(initial_channel)))
    return [ch] + [c for c in SWEEP_CHANNELS if c != ch]


def _register_dll_directories(config_dir: Path, settings_dir: Path | None = None) -> None:
    if sys.platform != "win32" or not hasattr(os, "add_dll_directory"):
        return

    candidates: list[Path] = []
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            mp = Path(meipass).resolve()
            candidates.extend([mp, mp / "xsensdeviceapi", mp / "xda_dll64"])
        exe_dir = Path(sys.executable).resolve().parent
        candidates.extend([exe_dir, exe_dir / "xda_dll64"])
    else:
        candidates.extend(
            [
                Path(__file__).resolve().parent.parent / "xda_sdk" / "dll64",
                Path(sys.prefix) / "Lib" / "site-packages" / "xsensdeviceapi",
            ]
        )

    candidates.extend(
        [
            Path(r"C:\Program Files\Movella"),
            Path(r"C:\Program Files\Xsens"),
            Path(r"C:\Program Files (x86)\Movella"),
            Path(r"C:\Program Files (x86)\Xsens"),
        ]
    )

    cfg_files: list[Path] = []
    if settings_dir is not None:
        cfg_files.append(settings_dir / "xda_paths.json")
    cfg_files.append(config_dir / "xda_paths.json")

    for xda_cfg in cfg_files:
        if xda_cfg.exists():
            try:
                data = json.loads(xda_cfg.read_text(encoding="utf-8"))
                for raw_dir in data.get("dll_dirs") or []:
                    candidates.append(Path(raw_dir))
                for py_dir in data.get("python_dirs") or []:
                    p = Path(py_dir)
                    if p.is_dir() and str(p) not in sys.path:
                        sys.path.insert(0, str(p))
            except Exception:
                pass

    seen: set[str] = set()
    for base in candidates:
        if not base.exists():
            continue
        key = str(base.resolve())
        if key not in seen:
            seen.add(key)
            try:
                _DLL_DIR_HANDLES.append(os.add_dll_directory(key))
            except OSError:
                pass
        if base.name.lower() in ("movella", "xsens"):
            for dll_name in ("xsensdeviceapi64.dll", "xstypes64.dll"):
                for dll in base.rglob(dll_name):
                    parent_key = str(dll.parent.resolve())
                    if parent_key not in seen:
                        seen.add(parent_key)
                        try:
                            _DLL_DIR_HANDLES.append(os.add_dll_directory(parent_key))
                        except OSError:
                            pass


def _load_locked_channel(settings_dir: Path | None, config_dir: Path) -> int | None:
    """Lee un canal RF bloqueado permanentemente desde awinda_radio.json si existe."""
    candidates: list[Path] = []
    if settings_dir is not None:
        candidates.append(settings_dir / "awinda_radio.json")
    candidates.append(config_dir / "awinda_radio.json")
    for cfg_path in candidates:
        if not cfg_path.exists():
            continue
        try:
            data = json.loads(cfg_path.read_text(encoding="utf-8"))
            raw_locked = data.get("locked_channel")
            if raw_locked is not None:
                ch = int(raw_locked)
                if 11 <= ch <= 25:
                    return ch
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            pass
    return None


def _save_winning_channel(
    settings_dir: Path | None,
    config_dir: Path,
    channel: int,
    rate_hz: int,
    station_id: str,
) -> None:
    target_dir = settings_dir if settings_dir is not None else (None if getattr(sys, "frozen", False) else config_dir)
    if target_dir is None:
        return
    try:
        ch = max(11, min(25, int(channel)))
        target_dir.mkdir(parents=True, exist_ok=True)
        out_path = target_dir / "awinda_radio.json"
        payload = {
            "channel": ch,
            "locked_channel": ch,
            "rate_hz": int(rate_hz),
            "station_id": station_id,
            "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass


def _normalize_enu_quat_to_yup(qw: float, qx: float, qy: float, qz: float) -> list[float]:
    w, x, y, z = float(qw), float(qx), float(qz), -float(qy)
    n = math.sqrt(w * w + x * x + y * y + z * z)
    if n < 1e-9:
        return [1.0, 0.0, 0.0, 0.0]
    return [w / n, x / n, y / n, z / n]


def run_worker(
    args: argparse.Namespace,
    xda_module: Any | None = None,
    emit_fn: Callable[[dict[str, Any]], None] | None = None,
    stop_event_override: threading.Event | None = None,
) -> int:
    config_dir = Path(args.config_dir)
    raw_settings_dir = getattr(args, "settings_dir", "") or ""
    settings_dir = Path(raw_settings_dir) if str(raw_settings_dir).strip() else None

    if xda_module is None:
        _register_dll_directories(config_dir, settings_dir=settings_dir)

    stop_event = stop_event_override or threading.Event()
    emit_lock = threading.Lock()

    def emit(payload: dict[str, Any]) -> None:
        if emit_fn is not None:
            emit_fn(payload)
            return
        line = json.dumps(payload, ensure_ascii=False)
        with emit_lock:
            try:
                sys.stdout.write(line + "\n")
                sys.stdout.flush()
            except (BrokenPipeError, OSError):
                stop_event.set()

    if xda_module is not None:
        xda = xda_module
    else:
        try:
            xda = importlib.import_module("xsensdeviceapi")
        except Exception as exc:
            emit(
                {
                    "type": "error",
                    "code": "xda_import_failed",
                    "message_es": f"No se pudo cargar xsensdeviceapi en Python 3.10: {exc}",
                }
            )
            return 3

    if getattr(args, "self_test_import", False):
        xda_version = ""
        try:
            ver_obj = xda.XsVersion()
            xda.xdaVersion(ver_obj)
            xda_version = ver_obj.toXsString()
        except Exception:
            xda_version = getattr(xda, "__version__", "") or "loaded"
        emit(
            {
                "type": "self_test",
                "ok": True,
                "xda_version": xda_version,
                "frozen": bool(getattr(sys, "frozen", False)),
            }
        )
        return 0

    if xda_module is None:
        def _on_signal(_signum: int, _frame: Any) -> None:
            stop_event.set()

        for sig_name in ("SIGINT", "SIGTERM", "SIGBREAK"):
            sig = getattr(signal, sig_name, None)
            if sig is not None:
                try:
                    signal.signal(sig, _on_signal)
                except (ValueError, OSError):
                    pass

        if stop_event_override is None:
            def _stdin_watcher() -> None:
                try:
                    for raw_line in sys.stdin:
                        if raw_line.strip().upper() in ("STOP", "QUIT", "EXIT"):
                            stop_event.set()
                            return
                except Exception:
                    pass
                stop_event.set()

            stdin_thread = threading.Thread(target=_stdin_watcher, name="XdaStdinWatcher", daemon=True)
            stdin_thread.start()

    max_runtime_timer: threading.Timer | None = None
    max_runtime = float(getattr(args, "max_runtime", 0.0) or 0.0)
    if max_runtime > 0.0:
        max_runtime_timer = threading.Timer(max_runtime, stop_event.set)
        max_runtime_timer.daemon = True
        max_runtime_timer.start()

    shared_lock = threading.Lock()
    connected_mtws: set[str] = set()
    battery_cache: dict[str, float] = {}
    last_pkt_ms: dict[str, float] = {}
    last_emitted_key: dict[str, tuple[str, int]] = {}
    station_id_ref = [""]
    target_rate_ref = [60.0]
    debug_seen: set[str] = set()

    def _debug_once(where: str, exc: BaseException | str) -> None:
        """Reporta por JSON cada tipo de incidencia una sola vez para que SWIG nunca la silencie."""
        err_txt = f"{type(exc).__name__}: {exc}" if isinstance(exc, BaseException) else str(exc)
        key = f"{where}:{err_txt}"
        with shared_lock:
            if key in debug_seen or len(debug_seen) >= 30:
                return
            debug_seen.add(key)
        emit({"type": "debug", "where": where, "error": err_txt})

    # Referencias fuertes para impedir recolección de basura de directores SWIG XsCallback
    active_callbacks: list[Any] = []
    attached_children: dict[str, tuple[Any, Any]] = {}

    xs_cb_base = getattr(xda, "XsCallback", object)

    class _MasterConnectivityCallback(xs_cb_base):  # type: ignore[misc, valid-type]
        def __init__(self) -> None:
            if xs_cb_base is not object:
                super().__init__()

        def onConnectivityChanged(self, dev: Any, newState: int) -> None:
            if dev is None:
                return
            try:
                did = dev.deviceId()
                if _is_master_or_dongle_id(did):
                    return
                sid = _device_id_str(did)
                if not sid or sid == "00000000" or sid == station_id_ref[0]:
                    return
                with shared_lock:
                    if newState in (xda.XCS_Wireless, xda.XCS_PluggedIn):
                        connected_mtws.add(sid)
                    elif newState in (xda.XCS_Disconnected, xda.XCS_Rejected, xda.XCS_WirelessOutOfRange):
                        connected_mtws.discard(sid)
            except Exception as exc:
                _debug_once("onConnectivityChanged", exc)

    class _MtwDataCallback(xs_cb_base):  # type: ignore[misc, valid-type]
        def __init__(self, expected_sid: str) -> None:
            if xs_cb_base is not object:
                super().__init__()
            self._expected_sid = expected_sid

        def onLiveDataAvailable(self, dev: Any, packet: Any) -> None:
            if stop_event.is_set() or packet is None:
                return
            try:
                sid = ""
                try:
                    sid = _device_id_str(packet.deviceId())
                except Exception:
                    sid = ""
                if (not sid or sid == "00000000") and dev is not None:
                    try:
                        sid = _device_id_str(dev.deviceId())
                    except Exception:
                        sid = ""
                if not sid or sid == "00000000":
                    sid = self._expected_sid
                if not sid or sid == "00000000" or sid == station_id_ref[0]:
                    return
                if not packet.containsOrientation():
                    return

                dedup_key: tuple[str, int] | None = None
                try:
                    if packet.containsPacketCounter():
                        dedup_key = ("cnt", int(packet.packetCounter()))
                    elif packet.containsSampleTimeFine():
                        dedup_key = ("stf", int(packet.sampleTimeFine()))
                    elif hasattr(packet, "packetId"):
                        pid = int(packet.packetId())
                        if pid > 0:
                            dedup_key = ("pid", pid)
                except Exception:
                    dedup_key = None

                q = packet.orientationQuaternion()
                q_out = _normalize_enu_quat_to_yup(q[0], q[1], q[2], q[3])

                if packet.containsFreeAcceleration():
                    fa = packet.freeAcceleration()
                    free_accel = [float(fa[0]), float(fa[2]), -float(fa[1])]
                elif packet.containsCalibratedAcceleration():
                    ca = packet.calibratedAcceleration()
                    free_accel = [float(ca[0]), float(ca[2]), -float(ca[1])]
                else:
                    free_accel = [0.0, 0.0, 0.0]

                if packet.containsCalibratedGyroscopeData():
                    gy = packet.calibratedGyroscopeData()
                    gyro = [float(gy[0]), float(gy[2]), -float(gy[1])]
                else:
                    gyro = [0.0, 0.0, 0.0]

                if packet.containsCalibratedMagneticField():
                    mg = packet.calibratedMagneticField()
                    mag = [float(mg[0]), float(mg[2]), -float(mg[1])]
                else:
                    mag = [0.0, 0.0, 1.0]

                rssi = int(packet.rssi()) if packet.containsRssi() else -52
                now_ms = time.monotonic() * 1000.0

                with shared_lock:
                    if dedup_key is not None and last_emitted_key.get(sid) == dedup_key:
                        return
                    if dedup_key is not None:
                        last_emitted_key[sid] = dedup_key

                    connected_mtws.add(sid)
                    prev = last_pkt_ms.get(sid)
                    hz = target_rate_ref[0]
                    if prev is not None and (now_ms - prev) > 0.5:
                        hz = min(240.0, 1000.0 / (now_ms - prev))
                    last_pkt_ms[sid] = now_ms
                    battery = battery_cache.get(sid, 85.0)

                emit(
                    {
                        "type": "packets",
                        "packets": [
                            {
                                "sensor_id": sid,
                                "quaternion": q_out,
                                "free_accel": free_accel,
                                "gyro": gyro,
                                "mag": mag,
                                "battery": battery,
                                "rssi": rssi,
                                "hz": round(float(hz), 1),
                                "timestamp_ms": now_ms,
                            }
                        ],
                    }
                )
            except Exception as exc:
                _debug_once("onLiveDataAvailable", exc)

    control = xda.XsControl_construct()
    if control is None:
        emit({"type": "error", "code": "control_construct_failed", "message_es": "No se pudo inicializar XsControl."})
        return 3

    master: Any = None
    port_name = ""
    master_cb: _MasterConnectivityCallback | None = None

    try:
        ports = xda.XsScanner_scanPorts()
        target_port = None
        req_port = str(getattr(args, "port", "") or "").strip().upper()
        port_count = ports.size() if hasattr(ports, "size") else len(ports)
        for i in range(port_count):
            pinfo = ports[i]
            did = pinfo.deviceId()
            if not _is_master_or_dongle_id(did):
                continue
            if req_port and str(pinfo.portName()).upper() != req_port:
                continue
            target_port = pinfo
            break

        if target_port is None:
            emit(
                {
                    "type": "error",
                    "code": "no_station",
                    "message_es": "No se detectó ninguna estación/antena Xsens Awinda conectada por USB.",
                }
            )
            return 2

        port_name = str(target_port.portName())
        baudrate = int(target_port.baudrate())
        did = target_port.deviceId()
        station_id = _device_id_str(did)
        station_id_ref[0] = station_id

        if not control.openPort(target_port):
            err_txt = control.lastResultText() if hasattr(control, "lastResultText") else "error de apertura"
            emit(
                {
                    "type": "error",
                    "code": "open_port_failed",
                    "port": port_name,
                    "message_es": f"XDA no pudo abrir el puerto {port_name} ({err_txt}).",
                }
            )
            return 4

        master = control.device(did)
        if master is None:
            emit(
                {
                    "type": "error",
                    "code": "device_lookup_failed",
                    "port": port_name,
                    "message_es": f"No se pudo obtener el dispositivo maestro XDA para {station_id}.",
                }
            )
            return 4

        config_ack = bool(master.gotoConfig())

        # Seleccionar tasa TDMA (Example_mtw: únicamente gotoConfig -> setUpdateRate -> enableRadio)
        target_rate = max(40, min(120, int(args.rate_hz)))
        try:
            supported = [int(r) for r in master.supportedUpdateRates()]
            if supported and target_rate not in supported:
                target_rate = 60 if 60 in supported else supported[0]
        except Exception:
            supported = [120, 100, 80, 60, 40]
        master.setUpdateRate(target_rate)
        try:
            actual_rate = int(master.updateRate())
            if actual_rate > 0:
                target_rate = actual_rate
        except Exception:
            pass
        target_rate_ref[0] = float(target_rate)

        # Solo conectividad en la estación maestra (nunca onAllDataAvailable ni salida redundante)
        master_cb = _MasterConnectivityCallback()
        active_callbacks.append(master_cb)
        master.addCallbackHandler(master_cb)

        def _read_current_children() -> dict[str, Any]:
            current: dict[str, Any] = {}
            try:
                kids = master.children()
                total = kids.size() if hasattr(kids, "size") else len(kids)
                for idx in range(total):
                    kid = kids[idx]
                    k_did = kid.deviceId()
                    sid = _device_id_str(k_did)
                    if not sid or sid == "00000000" or sid == station_id:
                        continue
                    try:
                        real_dev = control.device(k_did)
                    except Exception:
                        real_dev = None
                    current[sid] = real_dev if real_dev is not None else kid
            except Exception as exc:
                _debug_once("children", exc)
            return current

        def _collect_detected_ids() -> list[str]:
            current = _read_current_children()
            with shared_lock:
                ids = set(connected_mtws) | set(current.keys())
            return sorted(s for s in ids if s and s != station_id and s != "00000000")

        def _sync_child_callbacks() -> int:
            """Sincroniza callbacks por hijo real vía control.device(did), sin caché de punteros ni setOutputConfiguration."""
            current = _read_current_children()
            newly_attached = 0

            for old_sid in list(attached_children.keys()):
                if old_sid not in current:
                    old_dev, old_cb = attached_children.pop(old_sid)
                    try:
                        old_dev.removeCallbackHandler(old_cb)
                    except Exception:
                        pass
                    with shared_lock:
                        connected_mtws.discard(old_sid)

            for sid, mtw_dev in current.items():
                if sid not in attached_children:
                    child_cb = _MtwDataCallback(sid)
                    active_callbacks.append(child_cb)
                    mtw_dev.addCallbackHandler(child_cb)
                    attached_children[sid] = (mtw_dev, child_cb)
                    newly_attached += 1
                    with shared_lock:
                        connected_mtws.add(sid)
            return newly_attached

        def _refresh_battery_levels() -> None:
            for sid, (mtw_dev, _cb) in list(attached_children.items()):
                if hasattr(mtw_dev, "batteryLevel"):
                    try:
                        lvl = float(mtw_dev.batteryLevel())
                        if lvl > 0.0:
                            with shared_lock:
                                battery_cache[sid] = lvl
                    except Exception:
                        pass

        def _attempt_enter_measurement(max_attempts: int = 5, retry_delay_s: float = 0.6) -> tuple[bool, str]:
            last_err = ""
            for attempt in range(max_attempts):
                if stop_event.is_set():
                    break
                try:
                    if bool(master.gotoMeasurement()):
                        return True, ""
                except Exception as exc:
                    last_err = str(exc)
                try:
                    if hasattr(master, "lastResultText"):
                        txt = str(master.lastResultText() or "").strip()
                        if txt:
                            last_err = txt
                    elif hasattr(control, "lastResultText"):
                        txt = str(control.lastResultText() or "").strip()
                        if txt:
                            last_err = txt
                except Exception:
                    pass
                _debug_once("gotoMeasurement", f"Intento {attempt + 1}/{max_attempts} falló: {last_err or 'sin ACK'}")
                if attempt + 1 < max_attempts:
                    try:
                        master.gotoConfig()
                    except Exception:
                        pass
                    if stop_event.wait(retry_delay_s):
                        break
            return False, last_err or "La estación permaneció en Modo Config"

        raw_locked_arg = int(getattr(args, "locked_channel", 0) or 0)
        if raw_locked_arg < 0:
            effective_locked: int | None = None
        elif 11 <= raw_locked_arg <= 25:
            effective_locked = raw_locked_arg
        else:
            effective_locked = _load_locked_channel(settings_dir, config_dir)

        active_initial_ch = effective_locked if effective_locked is not None else max(11, min(25, int(args.channel)))

        emit(
            {
                "type": "station_ready",
                "station_id": station_id,
                "port": port_name,
                "baudrate": baudrate,
                "rate_hz": target_rate,
                "channel": active_initial_ch,
                "locked_channel": effective_locked,
                "config_ack": config_ack,
                "supported_rates": supported,
            }
        )

        # Barrido automático de canales (o canal bloqueado permanentemente sin cambios ante micro-interferencias)
        channel_order = [effective_locked] if effective_locked is not None else _build_channel_order(args.channel)
        winning_channel: int | None = None
        detected_ids: list[str] = []
        settle_s = max(0.05, float(getattr(args, "settle_wait_s", 2.5)))
        max_join_s = max(settle_s, float(getattr(args, "join_wait_s", 12.0)))
        locked_radio_enabled = False

        while not stop_event.is_set() and winning_channel is None:
            for ch in channel_order:
                if stop_event.is_set():
                    break
                if effective_locked is not None and locked_radio_enabled:
                    # En canal bloqueado, conservar la radio encendida sin reconfigurarla ante micro-cortes
                    pass
                else:
                    try:
                        if master.isRadioEnabled():
                            master.disableRadio()
                    except Exception:
                        pass

                    if not bool(master.enableRadio(ch)):
                        continue
                    if effective_locked is not None:
                        locked_radio_enabled = True

                    emit(
                        {
                            "type": "status",
                            "antenna_state": "radio_on",
                            "channel": ch,
                            "active_radio_channel": ch,
                            "locked_channel": effective_locked,
                            "radio_ack": True,
                            "measurement_ack": False,
                            "sweeping_channels": effective_locked is None,
                            "station_id": station_id,
                            "port": port_name,
                            "baudrate": baudrate,
                            "rate_hz": target_rate,
                            "detected_mtws": [],
                            "message_es": (
                                f"Motor Oficial XDA Activo · Canal RF Fijo {ch} · 0/17 Sensores"
                                if effective_locked is not None
                                else f"Motor Oficial XDA Activo · Canal RF {ch} · 0/17 Sensores"
                            ),
                        }
                    )

                dwell_end = time.monotonic() + float(args.dwell_s)
                found_here = False
                while not stop_event.is_set() and time.monotonic() < dwell_end:
                    c_count = 0
                    try:
                        c_count = int(master.childCount())
                    except Exception:
                        pass
                    detected_ids = _collect_detected_ids()
                    if c_count > 0 or detected_ids:
                        found_here = True
                        break
                    step = min(0.08, max(0.0, dwell_end - time.monotonic()))
                    if step > 0.0 and stop_event.wait(step):
                        break

                if found_here and not stop_event.is_set():
                    emit(
                        {
                            "type": "status",
                            "antenna_state": "radio_on",
                            "channel": ch,
                            "active_radio_channel": ch,
                            "locked_channel": ch,
                            "radio_ack": True,
                            "measurement_ack": False,
                            "sweeping_channels": False,
                            "station_id": station_id,
                            "port": port_name,
                            "baudrate": baudrate,
                            "rate_hz": target_rate,
                            "detected_mtws": detected_ids,
                            "message_es": f"Estabilizando sensores MTw en Canal RF {ch} ({len(detected_ids)}/17)...",
                        }
                    )

                    # Ventana reiniciable de 2.5 s cada vez que se suma un sensor (tope 12 s o 17 sensores)
                    join_max_end = time.monotonic() + max_join_s
                    settle_end = min(join_max_end, time.monotonic() + settle_s)
                    last_count = max(len(detected_ids), int(getattr(master, "childCount", lambda: 0)() or 0))
                    while not stop_event.is_set():
                        now_m = time.monotonic()
                        if now_m >= settle_end or now_m >= join_max_end:
                            break
                        c_count = 0
                        try:
                            c_count = int(master.childCount())
                        except Exception:
                            pass
                        detected_ids = _collect_detected_ids()
                        cur_count = max(len(detected_ids), c_count)
                        if cur_count > last_count:
                            last_count = cur_count
                            settle_end = min(join_max_end, now_m + settle_s)
                            emit(
                                {
                                    "type": "status",
                                    "antenna_state": "radio_on",
                                    "channel": ch,
                                    "active_radio_channel": ch,
                                    "locked_channel": ch,
                                    "radio_ack": True,
                                    "measurement_ack": False,
                                    "sweeping_channels": False,
                                    "station_id": station_id,
                                    "port": port_name,
                                    "baudrate": baudrate,
                                    "rate_hz": target_rate,
                                    "detected_mtws": detected_ids,
                                    "message_es": f"Estabilizando sensores MTw en Canal RF {ch} ({len(detected_ids)}/17)...",
                                }
                            )
                        if len(detected_ids) >= 17:
                            break
                        step = min(0.08, max(0.0, min(settle_end, join_max_end) - now_m))
                        if step > 0.0 and stop_event.wait(step):
                            break

                    detected_ids = _collect_detected_ids()
                    winning_channel = ch
                    effective_locked = ch
                    _save_winning_channel(settings_dir, config_dir, winning_channel, target_rate, station_id)
                    break

        if stop_event.is_set() or winning_channel is None:
            return 0

        # Esperar inicialización completa antes de pasar a medición (sin setOutputConfiguration)
        if hasattr(master, "waitForAllDevicesInitialized"):
            try:
                master.waitForAllDevicesInitialized()
            except Exception as exc:
                _debug_once("waitForAllDevicesInitialized", exc)

        _sync_child_callbacks()
        retry_delay_s = float(getattr(args, "meas_retry_delay_s", 0.6))
        meas_ok, last_err = _attempt_enter_measurement(max_attempts=5, retry_delay_s=retry_delay_s)
        if meas_ok:
            _sync_child_callbacks()
        _refresh_battery_levels()
        detected_ids = _collect_detected_ids()

        if meas_ok:
            init_state = "streaming" if last_pkt_ms else "radio_on"
            init_msg = f"Motor Oficial XDA Activo · Canal RF {winning_channel} · {len(detected_ids)}/17 Sensores"
        else:
            init_state = "error"
            init_msg = f"Error al pasar Awinda a modo medición (Canal RF {winning_channel}): {last_err}"

        emit(
            {
                "type": "status",
                "antenna_state": init_state,
                "channel": winning_channel,
                "active_radio_channel": winning_channel,
                "locked_channel": winning_channel,
                "radio_ack": True,
                "measurement_ack": meas_ok,
                "sweeping_channels": False,
                "station_id": station_id,
                "port": port_name,
                "baudrate": baudrate,
                "rate_hz": target_rate,
                "detected_mtws": detected_ids,
                "message_es": init_msg,
            }
        )

        last_meta_refresh = time.monotonic()
        last_battery_refresh = time.monotonic()
        last_meas_retry = time.monotonic()
        last_ids_snapshot = list(detected_ids)
        last_emitted_meas = meas_ok

        while not stop_event.is_set():
            now_mono = time.monotonic()
            if (now_mono - last_battery_refresh) >= 10.0:
                last_battery_refresh = now_mono
                _refresh_battery_levels()

            if (now_mono - last_meta_refresh) >= 0.5:
                last_meta_refresh = now_mono
                newly = _sync_child_callbacks()
                detected_ids = _collect_detected_ids()

                if (not meas_ok or newly > 0) and (now_mono - last_meas_retry) >= 3.0:
                    last_meas_retry = now_mono
                    if hasattr(master, "waitForAllDevicesInitialized"):
                        try:
                            master.waitForAllDevicesInitialized()
                        except Exception:
                            pass
                    ok_now, err_now = _attempt_enter_measurement(max_attempts=2, retry_delay_s=min(0.5, retry_delay_s))
                    if ok_now:
                        meas_ok = True
                        last_err = ""
                        _sync_child_callbacks()
                    elif not meas_ok:
                        last_err = err_now

                if detected_ids != last_ids_snapshot or meas_ok != last_emitted_meas:
                    last_ids_snapshot = list(detected_ids)
                    last_emitted_meas = meas_ok
                    emit(
                        {
                            "type": "status",
                            "antenna_state": ("streaming" if last_pkt_ms else "radio_on") if meas_ok else "error",
                            "channel": winning_channel,
                            "active_radio_channel": winning_channel,
                            "locked_channel": winning_channel,
                            "radio_ack": True,
                            "measurement_ack": meas_ok,
                            "sweeping_channels": False,
                            "station_id": station_id,
                            "port": port_name,
                            "baudrate": baudrate,
                            "rate_hz": target_rate,
                            "detected_mtws": detected_ids,
                            "message_es": (
                                f"Motor Oficial XDA Activo · Canal RF {winning_channel} · {len(detected_ids)}/17 Sensores"
                                if meas_ok
                                else f"Error al pasar Awinda a modo medición (Canal RF {winning_channel}): {last_err}"
                            ),
                        }
                    )

            stop_event.wait(0.1)

        return 0
    except Exception as exc:
        emit(
            {
                "type": "error",
                "code": "worker_exception",
                "port": port_name,
                "message_es": f"Error en puente XDA oficial: {exc}",
            }
        )
        return 1
    finally:
        stop_event.set()
        if max_runtime_timer is not None:
            max_runtime_timer.cancel()
        for mtw_dev, child_cb in list(attached_children.values()):
            try:
                mtw_dev.removeCallbackHandler(child_cb)
            except Exception:
                pass
        if master is not None and master_cb is not None:
            try:
                master.removeCallbackHandler(master_cb)
            except Exception:
                pass
        if master is not None:
            try:
                master.gotoConfig()
            except Exception:
                pass
            try:
                if master.isRadioEnabled():
                    master.disableRadio()
            except Exception:
                pass
        if port_name:
            try:
                control.closePort(port_name)
            except Exception:
                pass
        try:
            control.close()
        except Exception:
            pass
        try:
            control.destruct()
        except Exception:
            pass
        attached_children.clear()
        active_callbacks.clear()
        emit({"type": "stopped", "port": port_name})


def main() -> int:
    parser = argparse.ArgumentParser(description="Puente Xsens Device API (Python 3.10) para Awinda2.")
    parser.add_argument("--channel", type=int, default=11, help="Canal RF inicial (11..25)")
    parser.add_argument("--rate-hz", type=int, default=60, help="Frecuencia TDMA objetivo (Hz)")
    parser.add_argument("--port", type=str, default="", help="Puerto COM específico (opcional)")
    parser.add_argument(
        "--config-dir",
        type=str,
        default=str(Path(__file__).resolve().parent.parent / "config"),
        help="Directorio config de solo lectura de OpenMocap",
    )
    parser.add_argument(
        "--settings-dir",
        type=str,
        default="",
        help="Directorio escribible de configuración de usuario",
    )
    parser.add_argument("--max-runtime", type=float, default=0.0, help="Tiempo máximo en segundos (0 = ilimitado)")
    parser.add_argument("--dwell-s", type=float, default=3.0, help="Segundos por canal en barrido RF")
    parser.add_argument("--settle-wait-s", type=float, default=2.5, help="Ventana de estabilización reiniciable por MTw")
    parser.add_argument("--join-wait-s", type=float, default=12.0, help="Tope máximo de espera de unión MTw (s)")
    parser.add_argument("--meas-retry-delay-s", type=float, default=0.6, help="Espera entre reintentos de gotoMeasurement")
    parser.add_argument(
        "--locked-channel",
        type=int,
        default=0,
        help="Canal RF bloqueado (11..25; 0=leer awinda_radio.json; -1=permitir barrido)",
    )
    parser.add_argument("--self-test-import", action="store_true", help="Verifica carga de DLLs XDA sin abrir puertos COM")
    args = parser.parse_args()
    return run_worker(args)


if __name__ == "__main__":
    raise SystemExit(main())
