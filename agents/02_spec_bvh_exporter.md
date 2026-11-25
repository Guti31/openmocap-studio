# Nivel 2 — Agente Especialista #19: Exportador BVH Estándar para Blender (`spec_bvh_exporter`)

- **Orquestador Padre**: `04_orch_export_packaging`
- **Skill Especialista Asociada**: `.agent/skills/spec-bvh-exporter/SKILL.md`

## Responsabilidad Principal
Generar archivos .bvh limpios con jerarquía escalada al sujeto, canales Euler ZXY continuos y compatibilidad opcional con convenciones de nombres OpenMocap, Mixamo y Rigify.

## Archivos Bajo Propiedad
- `backend/export/bvh_exporter.py`

## Diseño Técnico y Contrato Operativo
Escribe sección HIERARCHY con offsets exactos en T-Pose y End Sites, aplica unwrap_euler_sequence sobre rotaciones locales para evitar discontinuidades de ±360°, inserta opcionalmente frame 0 en T-Pose e incluye validador estructural validate_bvh().

## Criterios de Verificación
Validación de jerarquía, 54 canales numéricos finitos por frame y presets mixamo/rigify en tests/verify_pipeline.py.
