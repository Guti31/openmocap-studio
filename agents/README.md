# Arquitectura Jerárquica Multi-Agente — OpenMocap Studio (APLICACION_TRAJE)

## Gobernanza y Jerarquía
- **Nivel 0 (Director Maestro)**: `00_master_director_orchestrator.md`
- **Nivel 1 (4 Orquestadores de Dominio)**:
  - `01_orch_hardware_hal.md`
  - `02_orch_kinematics_calibration.md`
  - `03_orch_studio_3d_ui.md`
  - `04_orch_export_packaging.md`
- **Nivel 2 (24 Agentes Especialistas + Skills `.agent/skills/spec-*/SKILL.md`)**:

| # | Agente Especialista | Skill Dedicada | Orquestador | Archivos Principales |
|---|---|---|---|---|
| 01 | [`02_spec_xsens_awinda_xda_driver.md`](./02_spec_xsens_awinda_xda_driver.md) | `spec-xsens-awinda-xda-driver` | `01_orch_hardware_hal` | `backend/hal/xsens_awinda_driver.py` |
| 02 | [`02_spec_serial_udp_multi_brand_driver.md`](./02_spec_serial_udp_multi_brand_driver.md) | `spec-serial-udp-multi-brand-driver` | `01_orch_hardware_hal` | `backend/hal/serial_udp_driver.py` |
| 03 | [`02_spec_ble_imu_scanner.md`](./02_spec_ble_imu_scanner.md) | `spec-ble-imu-scanner` | `01_orch_hardware_hal` | `backend/hal/ble_driver.py` |
| 04 | [`02_spec_17sensor_synthetic_simulator.md`](./02_spec_17sensor_synthetic_simulator.md) | `spec-17sensor-synthetic-simulator` | `01_orch_hardware_hal` | `backend/hal/synthetic_simulator.py` |
| 05 | [`02_spec_connection_watchdog_reconnector.md`](./02_spec_connection_watchdog_reconnector.md) | `spec-connection-watchdog-reconnector` | `01_orch_hardware_hal` | `backend/hal/watchdog.py` |
| 06 | [`02_spec_dynamic_sensor_mapper.md`](./02_spec_dynamic_sensor_mapper.md) | `spec-dynamic-sensor-mapper` | `01_orch_hardware_hal` | `backend/hal/sensor_mapper.py`, `backend/config/default_awinda_17.json` |
| 07 | [`02_spec_anthropometric_scaler.md`](./02_spec_anthropometric_scaler.md) | `spec-anthropometric-scaler` | `02_orch_kinematics_calibration` | `backend/kinematics/anthropometry.py` |
| 08 | [`02_spec_tpose_static_calibrator.md`](./02_spec_tpose_static_calibrator.md) | `spec-tpose-static-calibrator` | `02_orch_kinematics_calibration` | `backend/kinematics/calibration.py` |
| 09 | [`02_spec_dynamic_walk_calibrator.md`](./02_spec_dynamic_walk_calibrator.md) | `spec-dynamic-walk-calibrator` | `02_orch_kinematics_calibration` | `backend/kinematics/calibration.py` |
| 10 | [`02_spec_hierarchical_fk_solver.md`](./02_spec_hierarchical_fk_solver.md) | `spec-hierarchical-fk-solver` | `02_orch_kinematics_calibration` | `backend/kinematics/fk_solver.py` |
| 11 | [`02_spec_joint_angle_biomechanics.md`](./02_spec_joint_angle_biomechanics.md) | `spec-joint-angle-biomechanics` | `02_orch_kinematics_calibration` | `backend/kinematics/biomechanics.py` |
| 12 | [`02_spec_sensor_fusion_filter.md`](./02_spec_sensor_fusion_filter.md) | `spec-sensor-fusion-filter` | `02_orch_kinematics_calibration` | `backend/kinematics/sensor_fusion.py` |
| 13 | [`02_spec_desktop_shell_architect.md`](./02_spec_desktop_shell_architect.md) | `spec-desktop-shell-architect` | `03_orch_studio_3d_ui` | `frontend/electron/main.cjs`, `frontend/electron/preload.cjs`, `backend/main.py`, `backend/engine.py` |
| 14 | [`02_spec_threejs_mannequin_renderer.md`](./02_spec_threejs_mannequin_renderer.md) | `spec-threejs-mannequin-renderer` | `03_orch_studio_3d_ui` | `frontend/src/components/Viewport3D.tsx`, `frontend/src/components/MannequinScene.tsx` |
| 15 | [`02_spec_dockable_studio_panels.md`](./02_spec_dockable_studio_panels.md) | `spec-dockable-studio-panels` | `03_orch_studio_3d_ui` | `frontend/src/components/TopBar.tsx`, `frontend/src/components/LeftHardwarePanel.tsx`, `frontend/src/components/RightBiomechanicsPanel.tsx`, `frontend/src/App.tsx` |
| 16 | [`02_spec_calibration_wizard_ui.md`](./02_spec_calibration_wizard_ui.md) | `spec-calibration-wizard-ui` | `03_orch_studio_3d_ui` | `frontend/src/components/CalibrationWizardModal.tsx` |
| 17 | [`02_spec_anthropometric_profile_manager.md`](./02_spec_anthropometric_profile_manager.md) | `spec-anthropometric-profile-manager` | `03_orch_studio_3d_ui` | `frontend/src/components/ProfileManagerModal.tsx`, `backend/kinematics/anthropometry.py` |
| 18 | [`02_spec_take_recorder_timeline.md`](./02_spec_take_recorder_timeline.md) | `spec-take-recorder-timeline` | `03_orch_studio_3d_ui` | `backend/recording/recorder.py`, `frontend/src/components/TimelineBar.tsx` |
| 19 | [`02_spec_bvh_exporter.md`](./02_spec_bvh_exporter.md) | `spec-bvh-exporter` | `04_orch_export_packaging` | `backend/export/bvh_exporter.py` |
| 20 | [`02_spec_blender_fbx_bridge.md`](./02_spec_blender_fbx_bridge.md) | `spec-blender-fbx-bridge` | `04_orch_export_packaging` | `backend/export/blender_bridge.py`, `blender_tools/convertir_a_fbx.py`, `frontend/src/components/ExportModal.tsx` |
| 21 | [`02_spec_viewport_video_recorder.md`](./02_spec_viewport_video_recorder.md) | `spec-viewport-video-recorder` | `04_orch_export_packaging` | `frontend/src/hooks/useVideoRecorder.ts`, `backend/export/video_converter.py` |
| 22 | [`02_spec_bilingual_i18n_ux.md`](./02_spec_bilingual_i18n_ux.md) | `spec-bilingual-i18n-ux` | `04_orch_export_packaging` | `frontend/src/i18n/es.ts`, `frontend/src/i18n/en.ts`, `frontend/src/i18n/index.ts` |
| 23 | [`02_spec_desktop_packager_builder.md`](./02_spec_desktop_packager_builder.md) | `spec-desktop-packager-builder` | `04_orch_export_packaging` | `build/openmocap_backend.spec`, `frontend/package.json`, `INICIAR_ESTUDIO.bat`, `GENERAR_INSTALADOR.bat` |
| 24 | [`02_spec_end_to_end_qa_auditor.md`](./02_spec_end_to_end_qa_auditor.md) | `spec-end-to-end-qa-auditor` | `04_orch_export_packaging` | `tests/verify_pipeline.py` |
