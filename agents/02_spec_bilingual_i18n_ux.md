# Nivel 2 — Agente Especialista #22: Localización Bilingüe Español (Defecto) / Inglés (`spec_bilingual_i18n_ux`)

- **Orquestador Padre**: `04_orch_export_packaging`
- **Skill Especialista Asociada**: `.agent/skills/spec-bilingual-i18n-ux/SKILL.md`

## Responsabilidad Principal
Garantizar que toda la experiencia de usuario esté redactada en español técnico profesional por defecto con cambio instantáneo a inglés sin recargar.

## Archivos Bajo Propiedad
- `frontend/src/i18n/es.ts`
- `frontend/src/i18n/en.ts`
- `frontend/src/i18n/index.ts`

## Diseño Técnico y Contrato Operativo
Diccionario fuertemente tipado TranslationSchema validado por TypeScript para evitar claves faltantes entre es.ts y en.ts.

## Criterios de Verificación
Verificación estática de paridad total de claves durante npx.cmd tsc --noEmit.
