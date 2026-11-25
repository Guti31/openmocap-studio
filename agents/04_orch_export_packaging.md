# Nivel 1: Orquestador de Exportación, Video y Empaquetado (`04_orch_export_packaging`)

## Dominio de Responsabilidad
Convertir tomas capturadas en activos listos para producción en Blender (`.bvh` y `.fbx`), videos de demostración `.mp4` a 60 FPS, localización ES/EN completa, empaquetado `.exe` distribuible y auditoría QA automatizada.

## Agentes Especialistas Bajo Supervisión (6)
19. `spec_bvh_exporter`
20. `spec_blender_fbx_bridge`
21. `spec_viewport_video_recorder`
22. `spec_bilingual_i18n_ux`
23. `spec_desktop_packager_builder`
24. `spec_end_to_end_qa_auditor`

## Entregables en Código
- `backend/export/bvh_exporter.py`, `blender_bridge.py`, `video_converter.py`
- `blender_tools/convertir_a_fbx.py`
- `frontend/src/i18n/*`, `build/openmocap_backend.spec`, `INICIAR_ESTUDIO.bat`, `GENERAR_INSTALADOR.bat`, `tests/verify_pipeline.py`.
