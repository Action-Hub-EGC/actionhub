# Formato de paquete de workflow

- **Issues:** #14 (formato y subida), #15 y #16 (validación L1 y L2), #17 (metadatos), #21 (descarga y datos de ejemplo).
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
- `WorkflowVersion` con el manifiesto, el YAML del workflow y sus metadatos en `metadata_json` (ver «Metadatos del workflow»).
- Un `Hubfile` por archivo del paquete, con `workflow_version_id`.
- Los archivos se copian a `uploads/user_<id>/dataset_<id>/v<n>/` (`HubfileService.version_directory`, #37).

La publicación con DOI se describe en «Ciclo de vida».

## Ciclo de vida

Desde #19, `WorkflowDataset.validation_status` sigue este ciclo (`app/features/workflow/lifecycle.py`):

| Desde | Hacia | Cuándo |
|---|---|---|
| `draft` | `validated` / `failed` | Al validar la versión: L1 + L2 (`validate_l2_version`, o `upload_package`, que guarda directamente en `validated`) |
| `failed` | `validated` / `failed` | Al volver a validar |
| `validated` | `validated` / `failed` | Al volver a validar |
| `validated` | `published` | Al publicar con DOI |
| `published` | — | Ninguna: un workflow publicado es inmutable. Una versión nueva es WI-196 |

Cualquier otra transición (por ejemplo `draft` → `published`, o validar un workflow publicado) lanza `InvalidTransition` y no cambia nada. L4 (#18) añadirá su calificación de seguridad en el paso a `validated`.

**Publicar.** El propietario pulsa «Publicar con DOI» en la ficha (`POST /workflow/<id>/publish`). `WorkflowPublicationService.publish`:

1. comprueba que el workflow está `validated` y que su última versión tiene archivos;
2. crea la deposition (`POST /depositions`) y guarda `deposition_id` en `DSMetaData`;
3. sube los archivos de la última versión (`POST /depositions/{id}/files`). Zenodo no admite `/` en el nombre, así que `fixtures/input.txt` se sube como `fixtures__input.txt`;
4. publica (`POST /depositions/{id}/actions/publish`) y lee el DOI (`GET /depositions/{id}`);
5. guarda el DOI en `DSMetaData.dataset_doi` y pasa a `published`.

Si falla cualquier paso, el workflow sigue en `validated` y sin DOI, el usuario ve un mensaje genérico y el detalle queda en el log. Se puede reintentar. El destino es el que marque `ZENODO_API_URL`: con fakenodo, el DOI es `10.5072/fakenodo.<id>`. Solo el propietario puede publicar (`403` para el resto).

## Metadatos del workflow

Desde #17, cada `WorkflowVersion` guarda en `workflow_version.metadata_json` (texto JSON, migración `004`) un resumen de lo que hace el workflow, para poder verlo antes de descargarlo y comparar workflows:

| Campo | Contenido |
|---|---|
| `name` | `name` del workflow, o `null` |
| `triggers` | Eventos de `on`, en sus tres formas: cadena, lista o mapa. También se lee `on` cuando un cargador YAML 1.1 la convierte en `True` |
| `jobs` | Por job: `id`, `name`, `runs_on`, `matrix`, `actions` de sus pasos y `uses` si llama a un workflow reutilizable |
| `runners` | Etiquetas de `runs-on` sin repetir: cadena, lista o `group`/`labels`. `${{ matrix.<clave> }}` se resuelve a los valores de la matriz, incluido `include`; si no se puede resolver, se guarda tal cual |
| `actions` | `uses` de los pasos, sin repetir |
| `reusable_workflows` | `uses` a nivel de job, sin repetir |

**Cuándo se calculan.** Solo en `upload_package`, después de que el paquete pase todas las validaciones bloqueantes de `PackageValidator` (L1, L2 y la estructura de `workflow.yml`). El cálculo está en un único método, `WorkflowDatasetService.metadata_json_for`. `validate_l1_version` y `validate_l2_version` **no** extraen metadatos, para que no haya un segundo camino que los guarde. Si el documento no es un mapa YAML, el método devuelve `null` en vez de fallar.

**Dónde se muestran.** La ficha `/workflow/<id>` enseña los metadatos de la última versión (`WorkflowDataset.workflow_metadata()`, que usa `latest_version()`) en la tarjeta «Qué hace este workflow». Las versiones subidas antes de la migración `004` tienen `metadata_json = NULL` y la ficha lo indica.

## Descarga

`GET /workflow/<id>/download` (botón «Descargar paquete (.zip)» en la ficha) devuelve un ZIP con el paquete tal como se subió:

- Los archivos van en la raíz con sus nombres originales (`fixtures/input.txt` incluido), así que el ZIP vuelve a pasar `PackageValidator` y se puede subir otra vez.
- Se sirve la última versión publicada (con DOI) y, si no hay ninguna, la última versión.
- Las entradas salen de las filas `Hubfile` de esa versión, no de recorrer la carpeta, y las rutas de `HubfileService` (#37). Lo construye `WorkflowDatasetService.build_package_archive`.
- El nombre es `<name>-<version>.zip` del manifiesto, por ejemplo `demo-workflow-1.0.0.zip`.
- Cuenta una descarga por navegador con la misma cookie (`download_cookie`) y tabla (`ds_download_record`) que la descarga de datasets (#66, #67).
- Devuelve `404` si el workflow no existe o no tiene archivos.

La página pública del DOI (`/doi/<doi>/`) de un workflow enlaza a esta descarga. `/dataset/download/<id>` sigue siendo la descarga de los datasets UVL.

## Datos de ejemplo

`rosemary db:seed` ejecuta `WorkflowSeeder` (`app/features/workflow/seeders.py`, prioridad 3: después de usuarios y datasets UVL, antes de métricas). Cada carpeta de `app/features/workflow/seed_examples/` es un paquete con el formato de arriba; el seeder lo comprime, lo valida con `PackageValidator` y lo guarda por el mismo camino que una subida (`WorkflowDatasetService.store_package`): versión 1, `WorkflowVersion` con `metadata_json` y `Hubfile` con checksum y tamaño reales.

| Paquete | Nota | Puntuación | Estado | Por qué |
|---|---|---|---|---|
| `secure-node-ci` | A | 100 | publicado (`10.1234/workflow1`) | Todas las acciones fijadas por SHA y `permissions` mínimos: ninguna penalización |
| `python-test-matrix` | B | 85 | publicado (`10.1234/workflow2`) | `setup-python` por etiqueta (SEC-01, -15) |
| `docker-image-publish` | C | 70 | publicado (`10.1234/workflow3`) | `login-action` y `build-push-action` por etiqueta (SEC-01, -30) |
| `nightly-dependency-update` | D | 60 | borrador (`validated`) | Dos acciones por etiqueta (SEC-01, -30) y sin `permissions` (SEC-02, -10) |
| `issue-label-bot` | E | 55 | borrador (`validated`) | Tres acciones sin fijar, dos en `@main` (SEC-01, -45 con el tope) |
| `pr-preview-deploy` | F | 35 | publicado (`10.1234/workflow6`) | Dos acciones en `@master` (SEC-01, -30), `write-all` (SEC-03, -10) y `pull_request_target` con checkout del head (SEC-04, -25) |

La nota y la puntuación son las que dan las reglas L4 de #18 (SEC-01 a SEC-04) para cada `workflow.yml`. Mientras #18 no esté en `trunk`, el seeder las fija con esos mismos valores. Los publicados tienen DOI falso sin deposition: no se llama a Zenodo ni a fakenodo. Si un paquete ya existe (mismo `name`), el seeder no lo vuelve a crear.

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
- `app/features/workflow/lifecycle.py`
- `app/features/workflow/validation.py`
- `app/features/workflow/metadata.py`
- `app/features/workflow/seeders.py` y `app/features/workflow/seed_examples/`
- `app/features/workflow/schemas/actionhub.schema.json`
- `app/features/workflow/schemas/github-workflow.schema.json`
- `app/features/workflow/services.py`
- `app/features/workflow/routes.py`
- `app/features/workflow/tests/test_package.py`
- `app/features/workflow/tests/test_validation.py`
- `app/features/workflow/tests/test_metadata.py`
- `migrations/versions/004.py`
- `app/features/workflow/tests/test_lifecycle.py`
