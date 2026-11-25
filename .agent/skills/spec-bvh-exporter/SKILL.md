---
name: spec-bvh-exporter
description: Generar archivos .bvh limpios con jerarquía escalada al sujeto, canales Euler ZXY continuos y compatibilidad opcional con convenciones de nombres OpenMocap, Mixamo y Rigify.
---

# Skill Especialista: Exportador BVH Estándar para Blender

- **Agente Propietario**: `agents/02_spec_bvh_exporter.md`
- **Orquestador de Dominio**: `04_orch_export_packaging`

## Archivos Objetivo
- `backend/export/bvh_exporter.py`

## Especificación Algorítmica y Contratos
Escribe sección HIERARCHY con offsets exactos en T-Pose y End Sites, aplica unwrap_euler_sequence sobre rotaciones locales para evitar discontinuidades de ±360°, inserta opcionalmente frame 0 en T-Pose e incluye validador estructural validate_bvh().

## Criterios de Aceptación y Pruebas
Validación de jerarquía, 54 canales numéricos finitos por frame y presets mixamo/rigify en tests/verify_pipeline.py.
