# Nivel 2 — Agente Especialista #07: Escalador Antropométrico (Tablas de Winter) (`spec_anthropometric_scaler`)

- **Orquestador Padre**: `02_orch_kinematics_calibration`
- **Skill Especialista Asociada**: `.agent/skills/spec-anthropometric-scaler/SKILL.md`

## Responsabilidad Principal
Calcular longitudes anatómicas exactas de cada segmento óseo en metros a partir de la estatura obligatoria y medidas corporales opcionales del usuario.

## Archivos Bajo Propiedad
- `backend/kinematics/anthropometry.py`

## Diseño Técnico y Contrato Operativo
Aplica proporciones de Winter (muslo 0.245*H, pierna 0.246*H, pie altura 0.039*H, largo 0.152*H, hombro-codo 0.186*H, antebrazo 0.146*H, mano 0.108*H, etc.), ajusta proporcionalmente cuando el usuario introduce medidas directas y garantiza que en T-Pose la planta del pie quede en Y=0.0.

## Criterios de Verificación
Validación de longitudes positivas para múltiples estaturas (150-205 cm) y altura exacta en reposo igual a estatura.
