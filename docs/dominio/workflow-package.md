# Formato de paquete de workflow

- **Issue:** #14, #15, #16.
- **Formato:** un único archivo `.zip`.
- **Estado:** implementado; validación L1 (sintaxis YAML), L2 (esquema oficial de GitHub Actions) y esquema del manifiesto.

## Estructura

En la raíz del ZIP:

| Archivo | Obligatorio | Contenido |
|---|---|---|
| `actionhub.yaml` | Sí | Manifiesto del workflow |
| `workflow.yml` | Sí | Definición de GitHub Actions |
| `README.md` | Sí | Documentación del workflow |
| `LICENSE` | Sí | Licencia del paquete |
| `CHANGELOG.md` | No | Historial de cambios |
| `fixtures/` | No | Archivos auxiliares de ejemplo |

El ZIP puede envolver todo en una carpeta raíz; el validador la elimina. No se permiten rutas absolutas, `..`, enlaces simbólicos, archivos fuera de la lista ni duplicados.

## Manifiesto `actionhub.yaml`

```yaml
name: demo-workflow
version: 1.0.0
description: Un workflow de ejemplo para ActionHub
license: MIT
authors:
  - name: Ada Lovelace
    affiliation: Analytical Engine Lab
tags:
  - ci
  - demo
repository: [https://github.com/example/demo-workflow](https://github.com/example/demo-workflow)
```

### Campos

| Campo | Tipo | Obligatorio | Regla |
|---|---|---|---|
| `name` | string | Sí | Slug en minúsculas, 3–64 caracteres, guiones |
| `version` | string | Sí | SemVer, por ejemplo `1.0.0` |
| `description` | string | Sí | 10–500 caracteres |
| `license` | string | Sí | Identificador SPDX, por ejemplo `MIT` |
| `authors` | array | Sí | Al menos un autor con `name`; `email`, `url` y `affiliation` opcionales |
| `tags` | array | No | Máximo 10 etiquetas |
| `repository` | string | No | URL `http(s)` |
| `homepage` | string | No | URL `http(s)` |

El esquema completo está en `app/features/workflow/schemas/actionhub.schema.json`.

## Validación

Antes de guardar nada:

1. El archivo es un ZIP válido y no supera **10 MB**.
2. Están los cuatro archivos obligatorios.
3. `README.md` y `LICENSE` no están vacíos y son UTF-8.
4. `actionhub.yaml` pasa L1 (YAML bien formado y sin claves duplicadas) y el JSON Schema del manifiesto.
5. `workflow.yml` pasa L1 (sintaxis YAML y claves duplicadas) y **L2** (validación bloqueante contra el esquema oficial de GitHub Actions vendoreado en `app/features/workflow/schemas/github-workflow.schema.json`).

Si algo falla en L1, L2 o el manifiesto, se devuelven errores con archivo, campo y línea cuando están disponibles. **No se crea ningún dataset.**

## Esquemas

Los esquemas JSON viven en `app/features/workflow/schemas/` para garantizar validación determinista y sin acceso a red en local y en CI:

| Archivo | Propósito | Dialecto | Origen y licencia |
|---|---|---|---|
| `actionhub.schema.json` | Manifiesto de metadatos `actionhub.yaml` | Draft 2020-12 | Propio de ActionHub |
| `github-workflow.schema.json` | Validación L2 de `workflow.yml` | Draft-07 | [SchemaStore](https://json.schemastore.org/github-workflow.json) (`SchemaStore/schemastore`, licencia **Apache-2.0**) |

`github-workflow.schema.json` fue descargado de `https://json.schemastore.org/github-workflow.json` el **22 de noviembre de 2026**. Para refrescarlo manualmente:

```bash
curl -fsSL [https://json.schemastore.org/github-workflow.json](https://json.schemastore.org/github-workflow.json) -o app/features/workflow/schemas/github-workflow.schema.json
```

## Persistencia

Un paquete válido se guarda como **borrador no publicado**:

- `WorkflowDataset` con `validation_status='validated'`, `package_format='zip'` y sin DOI.
- `WorkflowVersion` con el manifiesto y el YAML del workflow.
- Un `Hubfile` por archivo del paquete, con `workflow_version_id`.
- Los archivos se copian a `uploads/user_<id>/dataset_<id>/`.

La publicación con DOI llega en #19/#31.

## Errores habituales

| Error | Causa |
|---|---|
| `Falta el archivo obligatorio: LICENSE` | El ZIP no contiene `LICENSE` en la raíz |
| `Manifiesto inválido: ...` | Un campo de `actionhub.yaml` no cumple el esquema |
| `Clave duplicada: ...` | `actionhub.yaml` o `workflow.yml` repite una clave |
| `Esquema inválido: ...` | `workflow.yml` no cumple el esquema oficial de GitHub Actions (p. ej. falta `on`, `jobs` o `runs-on`) |
| `Ruta no permitida dentro del ZIP` | Entrada con `..` o ruta absoluta |
| `Archivo no permitido en el paquete` | Archivo fuera de la estructura |

## Referencias

- `app/features/workflow/package.py`
- `app/features/workflow/validation.py`
- `app/features/workflow/schemas/actionhub.schema.json`
- `app/features/workflow/schemas/github-workflow.schema.json`
- `app/features/workflow/services.py`
- `app/features/workflow/routes.py`
- `app/features/workflow/tests/test_package.py`
- `app/features/workflow/tests/test_validation.py`