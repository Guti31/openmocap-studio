---
name: spec-bilingual-i18n-ux
description: Garantizar que toda la experiencia de usuario esté redactada en español técnico profesional por defecto con cambio instantáneo a inglés sin recargar.
---

# Skill Especialista: Localización Bilingüe Español (Defecto) / Inglés

- **Agente Propietario**: `agents/02_spec_bilingual_i18n_ux.md`
- **Orquestador de Dominio**: `04_orch_export_packaging`

## Archivos Objetivo
- `frontend/src/i18n/es.ts`
- `frontend/src/i18n/en.ts`
- `frontend/src/i18n/index.ts`

## Especificación Algorítmica y Contratos
Diccionario fuertemente tipado TranslationSchema validado por TypeScript para evitar claves faltantes entre es.ts y en.ts.

## Criterios de Aceptación y Pruebas
Verificación estática de paridad total de claves durante npx.cmd tsc --noEmit.
