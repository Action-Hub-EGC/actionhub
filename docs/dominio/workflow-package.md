# Formato de paquete de workflow

- **Issue:** #14.
- **Formato:** un único archivo `.zip`.
- **Estado:** implementado; validación L1 + esquema del manifiesto.

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
repository: https://github.com/example/demo-workflow
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
4. `actionhub.yaml` pasa L1 (YAML y claves duplicadas) y el JSON Schema.
5. `workflow.yml` pasa L1 y define `on` y al menos un `job`.

Si algo falla, se devuelven errores con archivo, campo y línea cuando están disponibles. **No se crea ningún dataset.**

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
| `Manifiesto inválido: ...` | Un campo no cumple el esquema |
| `Clave duplicada: ...` | `actionhub.yaml` repite una clave |
| `workflow.yml debe definir al menos un job` | Falta `jobs` o está vacío |
| `Ruta no permitida dentro del ZIP` | Entrada con `..` o ruta absoluta |
| `Archivo no permitido en el paquete` | Archivo fuera de la estructura |

## Referencias

- `app/features/workflow/package.py`
- `app/features/workflow/schemas/actionhub.schema.json`
- `app/features/workflow/services.py`
- `app/features/workflow/routes.py`
- `app/features/workflow/tests/test_package.py`
