# Diseño del versionado de datasets

- **Issue:** #35 · WI-196 (versionado mayor).
- **Fecha:** 20 de noviembre de 2026.
- **Autor:** José Fernando Gutiérrez (`@Jfgm299`).
- **Apoyo:** Francisco Casasola (`@Pacocc9`). Pendiente de su revisión.
- **Estado:** propuesta para revisión.
- **Alcance:** documentación. No se modifica código en #35.

## 1. Propósito

WI-196 pide que el propietario de un dataset publicado pueda cambiar sus archivos y publicar una versión nueva con un DOI nuevo, sin perder las anteriores. Antes de tocar el modelo hay que saber cómo se guardan hoy los archivos, qué hace el flujo de Zenodo y para qué sirve `DOIMapping`.

Este documento:

1. audita el almacenamiento de archivos, el flujo de Zenodo y `DOIMapping` en `trunk`;
2. compara las dos opciones del issue: una tabla `DatasetVersion` o una fila `DataSet` por versión enlazada por concept DOI;
3. registra la decisión y el diseño que implementarán #36, #37, #38 y #40;
4. comprueba que el diseño vale para UVL y para workflows a través de `BaseDataset`.

## 2. Estado actual

### 2.1. Modelo

| Pieza | Situación en `trunk` |
| --- | --- |
| `BaseDataset` (`data_set`) | Herencia de tabla única con discriminador `type` (`uvl`, `workflow`). Un dataset tiene un único `DSMetaData`. |
| `DSMetaData` | Guarda `deposition_id` y `dataset_doi`. **Un único DOI por dataset.** La presencia de `dataset_doi` define *publicado*. |
| UVL | `UVLDataset` → `FeatureModel` (N) → `Hubfile` (N). No existe ninguna noción de versión. |
| Workflow | `WorkflowDataset` → `WorkflowVersion` (N) → `Hubfile` (N). `WorkflowVersion` guarda el manifiesto y el YAML, pero no tiene número, DOI ni fecha de publicación. |
| `Hubfile` (`file`) | Cuelga de `feature_model_id` **o** de `workflow_version_id` (`ck_file_one_version`). Solo guarda `name`, no la ruta. |

*Publicado* (`dataset_doi IS NOT NULL`) se usa en `get_synchronized`, `count_synchronized_datasets`, `latest_synchronized` (`dataset/repositories.py`), en el explorador (`explore/repositories.py:40`) y en las métricas de #62 (`metrics/repositories.py`).

### 2.2. Almacenamiento de archivos

- Subida: los archivos van primero a `uploads/temp/<user_id>/` (`AuthenticationService.temp_folder_by_user`).
- Al crear el dataset se mueven a `uploads/user_<user_id>/dataset_<dataset_id>/` (`DataSetService.move_feature_models`, `dataset/services.py:52`).
- La ruta de un archivo se **reconstruye** a partir del propietario, el dataset y `Hubfile.name` (`HubfileService.get_path_by_hubfile`, `hubfile/services.py:36`).
- La descarga ZIP recorre la carpeta completa del dataset (`build_download_archive`, `dataset/services.py:231`).
- Desde #14 (#92, ya fusionado), `WorkflowDatasetService.upload_package` guarda los paquetes de workflow en la misma carpeta, con subcarpetas como `fixtures/`.

Hallazgos:

1. La misma ruta se construye en **cinco sitios** del código de aplicación, y en un sexto del seeder (se indica la línea donde empieza cada función):
   1. `DataSetService.move_feature_models` (`dataset/services.py:52`).
   2. `DataSetService.build_download_archive` (`dataset/services.py:231`).
   3. `HubfileService.get_path_by_hubfile` (`hubfile/services.py:36`).
   4. `ZenodoService.upload_file` (`zenodo/services.py:177`).
   5. `WorkflowDatasetService.upload_package` (`workflow/services.py:49`).
   6. `DataSetSeeder.run` (`dataset/seeders.py:18`).
2. `upload_file` usa `uploads_folder_name()`; los demás usan `WORKING_DIR/uploads`. Coinciden en Docker, pero no está garantizado.
3. La carpeta no distingue versiones. Si una versión nueva escribiera en ella, **sobrescribiría** los archivos de la anterior y el ZIP mezclaría versiones.

### 2.3. Flujo de Zenodo

`DataSetService.upload_dataset` (`dataset/services.py:182`):

1. `create_new_deposition` → `POST /depositions`.
2. Si la respuesta trae `conceptrecid`, guarda `id` como `deposition_id`. **`conceptrecid` solo se usa como bandera y se descarta.**
3. `upload_file` por cada `FeatureModel` → `POST /{id}/files`.
4. `publish_deposition` → `POST /{id}/actions/publish`.
5. `get_doi` → `GET /{id}` y guarda `doi` en `dataset_doi`. `conceptdoi` tampoco se guarda.

Hallazgos:

1. No hay llamada a `actions/newversion`. fakenodo la añadirá en #30; publicar llega en #29.
2. Si falla entre los pasos 2 y 5, el dataset queda con `deposition_id` pero sin DOI (respuesta `partial`). No hay reintento.
3. Si el paso 1 lanza una excepción, `upload_dataset` la captura y deja `zenodo_data = {}`. Como no hay `conceptrecid`, se saltan los pasos 2 a 5 y el método devuelve `"ok"`, no `"partial"`: el dataset queda sin `deposition_id` ni DOI y el usuario no recibe ningún aviso (`dataset/services.py:205-229`). #38 debe tratarlo como un fallo reintentable.
4. `get_zenodo_url` (`dataset/models.py:102`) construye `https://zenodo.org/record/<deposition_id>` a mano; se corrige en #32.
5. fakenodo ya guarda `conceptrecid` (igual al `id` en la primera versión) y una columna `version` (`fakenodo/store.py`).

### 2.4. `DOIMapping`

- Tabla `doi_mapping` con `dataset_doi_old` y `dataset_doi_new` (`dataset/models.py:195`).
- Solo la **lee** la ruta `/doi/<doi>/` (`dataset/routes.py:98`): si el DOI está mapeado, redirige con `302` al nuevo y busca `DSMetaData` por `dataset_doi`.
- **Nada la escribe** fuera de las pruebas. Es una redirección heredada de UVLHub para DOIs cambiados, no un historial de versiones.
- Con un único `dataset_doi` por dataset, el DOI de una versión antigua dejaría de resolver en cuanto se publicara la siguiente.

## 3. Opciones

### Opción A: tabla `dataset_version`

Un dataset es una fila de `data_set` y su concept DOI. Cada versión es una fila de `dataset_version` con su número, su deposition, su DOI y sus archivos.

### Opción B: una fila `data_set` por versión

Cada versión es un dataset completo (con su `DSMetaData`, sus autores y su carpeta). Las versiones se agrupan por `conceptrecid`.

### Comparación

| Criterio | A: `dataset_version` | B: filas enlazadas |
| --- | --- | --- |
| Catálogo, explorador, métricas (#62), contador (#9), insignia (#7) | Sin cambios: una fila por dataset. | Todas las consultas deben filtrar "última versión por concepto". Afecta a trabajo de otros WI. |
| Visitas y descargas | Se acumulan en el dataset. | Se reparten entre filas; hay que agregarlas por concepto. |
| Archivos por versión (#37) | Hace falta una subcarpeta `v<n>/`. | Gratis: cada versión tiene su `dataset_<id>/`. |
| DOI por versión (#40) | Una consulta más en `dataset_version.doi`. | Gratis: cada fila tiene su `dataset_doi`. |
| Datos duplicados | Ninguno. | `DSMetaData`, autores y métricas copiados en cada versión. |
| Encaje con el código de #12 | `FeatureModel` y `WorkflowVersion` pasan a colgar de una versión. Simétrico para los dos tipos. | `WorkflowVersion` queda 1:1 con su fila y pierde sentido. |
| Historial de versiones (#42) | `dataset.dataset_versions`. | Consulta por `conceptrecid`, que es nulo hasta publicar. |
| Datos existentes | Una versión 1 por dataset. | `conceptrecid` nulo en todo lo publicado; hay que inventar una clave de grupo. |

## 4. Decisión

**Se adopta la opción A: tabla `dataset_version` definida sobre `BaseDataset`.**

Motivos:

1. La identidad de un dataset para el usuario y para el resto de WI es la fila de `data_set`. Con A, el catálogo, las métricas, el contador y la insignia no cambian. Con B, cada una de esas tareas tendría que aprender a quedarse con la última versión.
2. Separa lo común de lo específico igual que #11 y #12: `dataset_version` es común; `FeatureModel` (UVL) y `WorkflowVersion` (workflow) son el contenido específico de una versión.
3. Lo que B da gratis (carpeta y DOI por versión) cuesta poco en A: una subcarpeta y una consulta.
4. No duplica metadatos ni autores.

Se descarta B por su impacto transversal en catálogo, explorador y métricas, que son trabajo de otros miembros del equipo.

## 5. Diseño

### 5.1. Modelo (#36)

Nueva tabla `dataset_version`:

| Columna | Tipo | Nulo | Notas |
| --- | --- | --- | --- |
| `id` | entero | no | Clave primaria. |
| `dataset_id` | entero | no | FK a `data_set.id`. |
| `number` | entero | no | Versión mayor: 1, 2, 3… Única por dataset. |
| `deposition_id` | entero | sí | Deposition de esta versión en Zenodo/fakenodo. |
| `doi` | cadena(120) | sí | DOI de esta versión. Nulo = borrador. |
| `change_note` | texto | sí | Nota corta de cambios. |
| `created_at` | datetime | no | Creación del borrador. |
| `published_at` | datetime | sí | Momento en que se obtuvo el DOI. |

Restricción: `UNIQUE (dataset_id, number)`.

Cambios en tablas existentes:

| Tabla | Cambio |
| --- | --- |
| `ds_meta_data` | Añadir `conceptrecid` (entero) y `concept_doi` (cadena 120). Son del dataset, no de una versión. |
| `ds_meta_data` | `deposition_id` y `dataset_doi` se mantienen y **reflejan la última versión publicada**. Así no cambian las consultas de *publicado*, el explorador ni las métricas. |
| `feature_model` | Añadir `dataset_version_id` (FK). |
| `workflow_version` | Añadir `dataset_version_id` (FK, único). `WorkflowVersion` pasa a ser el contenido de workflow de una versión. |
| `file` | Sin cambios: sigue colgando de `FeatureModel` o de `WorkflowVersion`. |

En `BaseDataset`:

- `dataset_versions`: relación con `DatasetVersion`, ordenada por `number`.
- `latest_dataset_version()` y `latest_published_dataset_version()`.
- `files_for_version(version=None)`: archivos de una versión; por defecto, la última publicada. Cada subtipo resuelve cómo llegar a ellos.

Los nombres no pueden ser `versions`, `latest_version()` ni `files()`: `WorkflowDataset` ya los define (`workflow/models.py:35-41`) y, en herencia declarativa, la subclase taparía los de `BaseDataset`. `workflow.versions` devolvería `WorkflowVersion` y no `DatasetVersion`, y el diseño común de la sección 6 no se cumpliría.

`WorkflowDataset` no cambia: `versions` y `latest_version()` siguen refiriéndose a `WorkflowVersion`, y `files()` sigue devolviendo todos los archivos del workflow. No se renombran para no tocar la plantilla ni los tests de #12 y #14.

Reglas:

- Como máximo un borrador (`doi IS NULL`) por dataset. Lo comprueba el servicio.
- Una versión con DOI es inmutable: no se cambian sus archivos ni su número.

### 5.2. Migración (#36)

1. Crear `dataset_version` y las columnas nuevas.
2. Por cada fila de `data_set`, crear la versión 1 con `deposition_id` y `doi = dataset_doi` de su `DSMetaData`. `published_at = created_at` si tiene DOI.
3. Rellenar `feature_model.dataset_version_id` con la versión 1 de su dataset.
4. Rellenar `workflow_version.dataset_version_id` con la versión 1 de su workflow. Hoy la relación es 1:1: el único sitio que crea una `WorkflowVersion` es `upload_package`, y siempre crea un workflow nuevo con una sola versión. Las versiones siguientes solo aparecerán con #38, que ya creará su `dataset_version`. Como `workflow_version.dataset_version_id` es único, la migración comprueba antes del paso 1 que ningún workflow tiene más de una `WorkflowVersion` y, si alguno la tiene, se detiene con un error que lo nombra, en vez de inventar números de versión o DOIs.
5. `conceptrecid` y `concept_doi` quedan nulos en los datasets existentes: nunca se guardaron. Se pueden recuperar con `GET /depositions/{id}` en un comando aparte; no se hace en la migración.
6. `downgrade` borra columnas y tabla. No toca archivos.

### 5.3. Archivos por versión (#37)

- Nueva ruta: `uploads/user_<user_id>/dataset_<dataset_id>/v<number>/<name>`.
- La ruta se calcula en **un solo sitio**, por ejemplo `HubfileService.version_dir(dataset, version)`, y la usan los seis puntos de 2.2 (cinco de aplicación y el seeder). Con eso se corrige también la diferencia entre `uploads_folder_name()` y `WORKING_DIR/uploads`.
- Compatibilidad: **no se mueven archivos en la migración**. Si `v1/` no existe, la versión 1 se lee de la carpeta antigua `dataset_<id>/`. Así, los datasets existentes y los workflows subidos con `upload_package` antes de #37 siguen descargándose.
- La descarga ZIP es de una versión: recorre solo `v<n>/` (o la carpeta antigua para v1 sin `v1/`, sin entrar en subcarpetas `v*/`).
- Una versión nueva copia los archivos de la anterior a `v<n+1>/` y aplica ahí las altas, cambios y bajas. Nunca se escribe en la carpeta de una versión publicada.

### 5.4. Flujo de una versión nueva (#38)

Primera publicación (sin cambios de fondo respecto a hoy):

1. `POST /depositions` → guardar `deposition_id` en la versión 1 y `conceptrecid` en `DSMetaData`.
2. Subir archivos y publicar.
3. Guardar `doi` y `published_at` en la versión y `concept_doi` en `DSMetaData` si la respuesta lo trae.
4. Actualizar `DSMetaData.deposition_id` y `dataset_doi` con los de la versión.

Versión nueva:

1. `POST /depositions/{deposition_id de la última versión}/actions/newversion`.
2. Crear `dataset_version` con `number = última + 1`, `doi` nulo y el `deposition_id` del borrador nuevo.
3. Copiar archivos a `v<n>/`; aplicar altas, cambios y bajas; reflejarlas en la deposition.
4. Workflows: repetir L1, L2 y la nota L4 antes de pasar a `validated`.
5. Publicar → guardar `doi` y `published_at`; actualizar `DSMetaData`.
6. Si algo falla, la versión queda como borrador y se puede reintentar. La versión anterior sigue publicada e intacta.

Contrato que necesitamos de fakenodo (#30): Zenodo devuelve el borrador nuevo en `links.latest_draft`. fakenodo debe devolver ese mismo campo, o su `id` directamente, y mantener el `conceptrecid`.

### 5.5. Resolución de DOIs (#40)

`/doi/<doi>/` resuelve en este orden:

1. `DOIMapping`: redirección heredada, sin cambios.
2. `dataset_version.doi`: página del dataset en esa versión.
3. `ds_meta_data.concept_doi`: página del dataset en su última versión.
4. Si no hay coincidencia: 404.

Con `dataset_version.doi` no hace falta escribir cada DOI de versión en `DOIMapping`, como sugiere el texto de #40. `DOIMapping` queda para DOIs que cambian de verdad. Se propone a `@Pacocc9`, responsable de #40, ajustar el issue.

### 5.6. Lo que no cambia

- Catálogo, explorador, métricas, contador e insignia: una fila por dataset, *publicado* sigue siendo `dataset_doi IS NOT NULL`.
- Visitas y descargas se registran por dataset. Contarlas por versión queda fuera de WI-196.
- Título, descripción, autores y etiquetas son del dataset y no se versionan.

## 6. Validez para cada tipo

| Pieza | UVL | Workflow |
| --- | --- | --- |
| Versión | `dataset_version` | `dataset_version` |
| Contenido de la versión | `FeatureModel` con `dataset_version_id` | `WorkflowVersion` con `dataset_version_id` |
| Archivos | `Hubfile` vía `FeatureModel` | `Hubfile` vía `WorkflowVersion` |
| Carpeta | `dataset_<id>/v<n>/` | `dataset_<id>/v<n>/` (con subcarpetas como `fixtures/`) |
| Validación al crear versión | La de UVL actual | L1, L2 y L4 (#38) |
| DOI y concept DOI | `dataset_version.doi` y `ds_meta_data.concept_doi` | Igual |

`BaseDataset` define la versión, la ruta y la resolución de DOIs; cada subtipo solo aporta su contenido.

## 7. Riesgos y preguntas abiertas

1. **Número de versión y manifiesto.** El manifiesto de workflow usa SemVer (`version: 1.0.0`, #92) y el hub usa una versión mayor entera. Propuesta para #38: exigir que el mayor del manifiesto coincida con `dataset_version.number`.
2. **Respuesta de `newversion` en fakenodo** (#30). Si no sigue a Zenodo, #38 queda bloqueado.
3. **`conceptrecid` de los datasets existentes** es nulo. Su concept DOI no resolverá hasta recuperarlo.
4. **`upload_package` (#92, fusionado) escribe en `dataset_<id>/`.** La compatibilidad de 5.3 cubre los workflows ya subidos; #37 cambia esa ruta a `v1/` para los nuevos.
5. **Fallos de Zenodo sin reintento.** Hoy un fallo deja el dataset sin DOI, con `partial` o incluso con `ok` si falla la creación de la deposition (2.3). #38 debe permitir reintentar la publicación de un borrador.

## 8. Impacto en otros issues

| Issue | Qué toma de este documento |
| --- | --- |
| #36 | Modelo de 5.1 y migración de 5.2. |
| #37 | Ruta, compatibilidad y descarga de 5.3. |
| #38 | Flujo de 5.4 y preguntas 1 y 5. |
| #40 | Orden de resolución de 5.5. Propuesta de ajuste del issue. |
| #42, #44, #45 | `dataset.dataset_versions`, descarga por versión y concept DOI. |
| #30 | Forma de la respuesta de `newversion`. |

## 9. Referencias

- `app/features/dataset/models.py`
- `app/features/dataset/services.py`
- `app/features/dataset/routes.py`
- `app/features/dataset/repositories.py`
- `app/features/hubfile/services.py`
- `app/features/hubfile/models.py`
- `app/features/workflow/models.py`
- `app/features/workflow/services.py`
- `app/features/dataset/seeders.py`
- `app/features/zenodo/services.py`
- `fakenodo/store.py`
- [Auditoría de llamadas a Zenodo](../zenodo-api-audit.md)
- [Auditoría del código UVL](uvl-audit.md)
