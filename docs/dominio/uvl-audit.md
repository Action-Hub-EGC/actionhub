# Auditoría del código UVL y separación común / específico

- **Issue:** #10 · WI #178 (`newdataset`).
- **Fecha:** 18 de noviembre de 2026.
- **Autor:** Marcos Á. Ayala (`@GBK4935`), en sustitución de José Fernando Gutiérrez por carga de trabajo.
- **Apoyo:** Jaime García-Castillejo (`@JaimeGarcia2005`).
- **Estado:** propuesta para revisión.
- **Alcance:** documentación. No se modifica código en #10.

## 1. Propósito

El código heredado de UVLHub está construido alrededor de un único tipo de dataset: modelos UVL. ActionHub necesita dos tipos:

- `UVLDataset`, que conserva el comportamiento actual sin regresiones.
- `WorkflowDataset`, que representa workflows de GitHub Actions.

Antes de refactorizar hay que saber **qué es común**, **qué es específico de UVL** y **qué es específico de workflow**. Este documento fija esa separación, decide dónde va cada pieza y registra la decisión de mantener `flamapy` exclusivamente para UVL.

## 2. Método

Se han revisado:

- modelos, repositorios, servicios, rutas y formularios de `dataset`, `featuremodel`, `hubfile`, `flamapy`, `explore`, `public`, `profile` y `zenodo`;
- plantillas de subida, listado, vista y exploración;
- seeders y ejemplos;
- dependencias de `requirements.txt` y `pyproject.toml`.

Criterio de clasificación:

| Clasificación | Significado |
| --- | --- |
| **Común** | Describe cualquier dataset, independientemente de su tipo. Va a `BaseDataset` o a infraestructura compartida. |
| **UVL** | Depende de la semántica de modelos de características, de `flamapy` o de archivos `.uvl`. Va a `UVLDataset` o a la feature `flamapy`. |
| **Workflow** | Depende de GitHub Actions, del manifiesto `actionhub.yaml`, de `actionlint` o de la calificación de seguridad. Va a `WorkflowDataset` o a la feature `workflow`. |
| **Compartido a refactorizar** | Es type-agnostic en concepto, pero hoy asume UVL. Se queda en infraestructura común y se generaliza. |

## 3. Modelo actual y modelo objetivo

| Hoy | Objetivo | Estrategia |
| --- | --- | --- |
| `DataSet` | `BaseDataset` | Mantener la tabla `data_set`, añadir discriminador `type` y alias `DataSet = BaseDataset` |
| — | `UVLDataset` | Subclase polimórfica con identidad `uvl` |
| — | `WorkflowDataset` | Subclase polimórfica con identidad `workflow` |
| `FeatureModel` | Versión UVL | Se mantiene el nombre en M2 para no romper FKs ni tests |
| `FMMetaData` | Metadatos de versión UVL | Se mantiene; `uvl_filename` y `uvl_version` son UVL |
| `Hubfile` | Archivo genérico | Se mantiene; `feature_model_id` se renombrará a `version_id` en una migración posterior |
| `DSMetrics`, `FMMetrics` | Métricas UVL | Se mueven al ámbito UVL; no se usan en workflow |
| `DSDownloadRecord`, `DSViewRecord` | Actividad del dataset base | Se mantienen en común |
| `DOIMapping` | Redirección de DOI | Común |

## 4. Decisión de herencia para M2

Se adopta **herencia de tabla única** (*single-table inheritance*) para el primer corte:

- `BaseDataset` mapea la tabla `data_set`.
- Se añade una columna `type` con `server_default="uvl"`.
- `UVLDataset` usa `polymorphic_identity="uvl"`.
- `WorkflowDataset` usa `polymorphic_identity="workflow"`.
- Las columnas específicas de workflow son nullables.

### Por qué

1. **Migración mínima:** no hay que crear una tabla base nueva ni mover las FKs existentes (`feature_model.data_set_id`, `ds_download_record.dataset_id`, etc.).
2. **Compatibilidad:** los imports actuales de `DataSet` siguen funcionando mediante un alias.
3. **Consultas polimórficas:** `BaseDataset.query` devuelve instancias de `UVLDataset` o `WorkflowDataset` según el discriminador.
4. **Riesgo controlado:** si el enfoque no convence, se puede migrar a tablas separadas en M3 sin cambiar la interfaz de los servicios.

### Coste

- La tabla `data_set` se ensancha con columnas de workflow.
- Algunas columnas serán nullables aunque solo apliquen a un tipo.
- Es aceptable para dos tipos y un proyecto de cinco semanas; la alternativa de tablas separadas añade una migración de datos que no aporta valor inmediato.

### Alternativa descartada por ahora

**Herencia de tabla unida** (`base_dataset` + `uvl_dataset` + `workflow_dataset`): más limpia a largo plazo, pero exige recrear FKs y migrar datos. Se reevaluará en M3 si el modelo crece.

## 5. Clasificación de puntos concretos

### 5.1. Común: va a `BaseDataset` o a infraestructura compartida

| ID | Punto | Dónde | Por qué es común | Destino | Acción |
| --- | --- | --- | --- | --- | --- |
| C1 | Identidad, propietario y fecha | `dataset/models.py` (`DataSet`) | No dependen del tipo | `BaseDataset` | Mover |
| C2 | Título, descripción, tipo de publicación, DOIs, tags | `dataset/models.py` (`DSMetaData`) | Metadatos de cualquier dataset | `BaseDataset` | Mantener |
| C3 | Autores | `dataset/models.py` (`Author`) | Comunes a cualquier publicación | `BaseDataset` | Mantener |
| C4 | Descargas y visitas | `dataset/models.py` (`DSDownloadRecord`, `DSViewRecord`) | Actividad del dataset base | Compartido | Mantener; joins por `dataset_id` |
| C5 | Redirección de DOI | `dataset/models.py` (`DOIMapping`) | Común a cualquier tipo | Compartido | Mantener |
| C6 | Archivo: nombre, checksum, tamaño | `hubfile/models.py` (`Hubfile`) | Un workflow también tiene archivos | Compartido | Mantener; en #12 añadir `workflow_version_id` nullable y unificar a `version_id` en #196 |
| C7 | URL de Zenodo, número y tamaño de archivos | `dataset/models.py` | No dependen del tipo | `BaseDataset` | Mover |
| C8 | URL pública del DOI | `dataset/models.py::get_uvlhub_doi`, `dataset/services.py::get_uvlhub_doi` | Nombre heredado, concepto común | `BaseDataset` | Renombrar a `get_public_doi` y mantener alias |
| C9 | Serialización común | `dataset/models.py::to_dict` | Campos comunes; los archivos son type-specific | `BaseDataset` | Dividir en `to_dict` + `to_dict_type` |
| C10 | Tipo de publicación científica | `dataset/models.py` (`PublicationType`) | Metadato común; no es el tipo de workflow | Compartido | Mantener; no confundir con `dataset.type` |
| C11 | Tamaño legible | `dataset/services.py` (`SizeService`) | Común | Compartido | Mantener |
| C12 | ZIP de descarga | `dataset/services.py::build_download_archive` | Común | `BaseDataset` | Mantener |
| C13 | Métricas de perfil | `app/features/metrics` | Comunes | Compartido | Mantener |
| C14 | Búsqueda por título, descripción, autor y tags | `explore/repositories.py` | Común | Compartido | Extraer filtros comunes |

### 5.2. UVL: va a `UVLDataset`, `FeatureModel` o `flamapy`

| ID | Punto | Dónde | Por qué es UVL | Destino | Acción |
| --- | --- | --- | --- | --- | --- |
| U1 | `FeatureModel` | `featuremodel/models.py` | Modelo de versión UVL | `UVLDataset` | Mantener como versión UVL; documentar |
| U2 | `FMMetaData.uvl_filename` | `featuremodel/models.py` | Nombre del archivo `.uvl` | `UVLDataset` | Mantener; no subir a `BaseDataset` |
| U3 | `FMMetaData.uvl_version` | `featuremodel/models.py` | Versión del modelo UVL | `UVLDataset` | Mantener; no subir a `BaseDataset` |
| U4 | `DSMetrics.number_of_models` / `number_of_features` | `dataset/models.py` | Métricas de modelos de características | `UVLDataset` | Mover; hoy son datos estáticos del seeder |
| U5 | `FMMetrics.solver` / `not_solver` | `featuremodel/models.py` | Métricas de SAT/flamapy | `UVLDataset` | Mover; no usar en workflow |
| U6 | Validación UVL | `flamapy/services.py::validate_uvl` | Parser ANTLR de UVL | Solo UVL | Mantener; import perezoso |
| U7 | Export Glencoe, SPLOT y CNF | `flamapy/services.py::export` | Transformaciones de feature models | Solo UVL | Mantener; no exponer en workflow |
| U8 | Rutas `/flamapy/*` | `flamapy/routes.py` | API específica de UVL | Solo UVL | Mantener; no registrar en workflow |
| U9 | `save_temp_uvl` | `dataset/services.py` | Acepta y guarda `.uvl` | Subida UVL | Generalizar en #14; el tipo decide el filtro |
| U10 | `move_feature_models` | `dataset/services.py` | Mueve archivos `.uvl` | Subida UVL | Generalizar en #14 |
| U11 | `FeatureModelForm` y campos UVL | `dataset/forms.py` | Formulario de modelo UVL | UI UVL | Separar formulario por tipo |
| U12 | Dropzone `acceptedFiles: '.uvl'` | `upload_dataset.html` | Acepta solo `.uvl` | UI UVL | Filtro por tipo; #14 |
| U13 | Formulario UVL dinámico | `upload_dataset.html` | Campos `uvl_filename`, `uvl_version` | UI UVL | Parcial UVL; #14 |
| U14 | Vista "UVL models" y botones flamapy | `view_dataset.html` | Check, export y nombres UVL | Vista UVL | Parcial UVL; el workflow tendrá otra vista |
| U15 | Filtro por `FMMetaData.uvl_filename` | `explore/repositories.py` | Búsqueda UVL | Búsqueda UVL | Hacer la búsqueda type-aware en #194 |
| U16 | `uvl_examples/` y seeds | `dataset/seeders.py`, `dataset/uvl_examples/` | 12 modelos UVL de ejemplo | Seed UVL | Mantener para regresión; workflow seeds en #21 |
| U17 | `ZenodoService` usa `uvl_filename` y `uvlhub` | `zenodo/services.py` | Asume nombre UVL y keyword UVLHub | Compartido a generalizar | Usar `file.name` y keyword configurable |
| U18 | Copy de UVLHub en público, equipo y base | `public/index.html`, `team/index.html`, `base_template.html` | Branding heredado | Deuda UI | Actualizar en #72/#76 |
| U19 | Docstring "UVL content" | `hubfile/services.py::read_text` | El archivo es genérico | Compartido | Renombrar a "contenido del archivo" |
| U20 | `get_uvlhub_doi` en la API | `dataset/api.py` | Nombre heredado | Compartido | Renombrar y añadir `type` |
| U21 | Dependencias `flamapy`, `uvlparser`, ANTLR | `requirements.txt`, `pyproject.toml` | Solo las necesita UVL | Solo UVL | Mantener; no importar desde módulos comunes |

### 5.3. Workflow: va a `WorkflowDataset` o a la feature `workflow`

| ID | Punto | Dónde | Por qué es workflow | Destino | Acción |
| --- | --- | --- | --- | --- | --- |
| W1 | `WorkflowDataset` | Nuevo | Tipo nuevo | `WorkflowDataset` | #12 |
| W2 | Manifiesto `actionhub.yaml` | Nuevo | Metadatos del workflow | `WorkflowDataset` | #12/#14 |
| W3 | `workflow.yml` | Nuevo | Definición de GitHub Actions | `WorkflowVersion` | #12/#14 |
| W4 | `WorkflowVersion` | Nuevo | Versión del workflow | `WorkflowDataset` | #12; archivos adicionales vía `Hubfile.workflow_version_id` |
| W5 | L1: sintaxis YAML y claves duplicadas | Nuevo | Validación de workflows | Servicio de validación | #15 |
| W6 | L2: JSON Schema del manifiesto | Nuevo | Validación de esquema | Servicio de validación | #16 |
| W7 | L3: `actionlint` | Nuevo | Análisis estático de workflows | Servicio de validación | #15/#18 |
| W8 | L4: reglas de seguridad | Nuevo | Riesgos de Actions | Servicio de validación | #18 |
| W9 | Calificación A–F | Nuevo | Resultado de L1–L4 | `WorkflowDataset` | #18 |
| W10 | Subida de paquete (ZIP o varios archivos) | Nuevo | Formato del workflow | UI workflow | #14 |
| W11 | Vista y badge del workflow | Nuevo | Producto | UI workflow | #213 |
| W12 | Facetas de workflow | Nuevo | Búsqueda | Explore | #194 |
| W13 | Seeds de workflows | Nuevo | Datos de prueba | Seed workflow | #21 |

### 5.4. Compartido que hoy asume UVL

| ID | Punto | Dónde | Problema | Acción |
| --- | --- | --- | --- | --- |
| S1 | `ExploreRepository.filter` une `FeatureModel` y `FMMetaData` sin condición | `explore/repositories.py` | Excluye datasets sin feature model y sesga la búsqueda a UVL | Refactor type-aware en #194/#20 |
| S2 | `DataSetRepository` | `dataset/repositories.py` | Nombres y consultas heredadas | Renombrar a `BaseDatasetRepository`, mantener alias |
| S3 | Contadores y últimos datasets | `public/routes.py` | Deben contar ambos tipos | Usar `BaseDataset` |
| S4 | `ZenodoService.upload_file` | `zenodo/services.py` | Usa `fm_meta_data.uvl_filename` | Aceptar un nombre de archivo genérico |
| S5 | `DataSetSeeder` | `dataset/seeders.py` | Solo crea UVL | Dividir en seeder UVL y seeder workflow |
| S6 | Serialización de la API | `dataset/api.py` | Solo campos comunes | Añadir `type` y campos por tipo |
| S7 | Plantilla de perfil | `profile/summary.html` | Usa `get_uvlhub_doi` | Renombrar al alias común |
| S8 | Portada pública | `public/index.html` | Copy y branding UVL | Actualizar en #72/#76 |
| S9 | Plantilla base | `base_template.html` | Canonical y branding UVL | Actualizar en #72/#76 |
| S10 | Imports de `DataSet` | Varios | Nombre heredado | Alias `DataSet = BaseDataset` durante la transición |

## 6. Decisión: `flamapy` solo para UVL

`flamapy` es una librería de modelos de características: lee UVL, valida la sintaxis del modelo y exporta a Glencoe, SPLOT y DIMACS. **No entiende de GitHub Actions.** Un workflow no es un modelo de características y no se puede validar con `flamapy`.

Por tanto:

1. `flamapy` se queda en `app/features/flamapy/` y en los servicios de `UVLDataset`.
2. `BaseDataset` y `WorkflowDataset` **no importan** `flamapy` ni `uvlparser`.
3. Las importaciones de `flamapy` se harán de forma perezosa dentro de los métodos de UVL, para que un despliegue que solo use workflows no cargue ANTLR al arrancar.
4. `WorkflowDataset` usará:
   - `ruamel.yaml` para L1 (sintaxis y claves duplicadas);
   - `jsonschema` para L2 (manifiesto `actionhub.yaml`);
   - `actionlint` para L3 (análisis estático);
   - reglas propias para L4 (permisos, `pull_request_target`, secretos, acciones sin pin, etc.).
5. La nota A–F se calcula a partir de L1–L4 y se guarda en `WorkflowDataset`; no se mezcla con `FMMetrics`.

**Consecuencia para CI:** `flamapy` sigue instalado para los tests de UVL y regresión. `actionlint` se añadirá como dependencia de la imagen o como binario descargado en el pipeline cuando se implemente #18.

## 7. Plan de migración

### 7.1. #11 · Extraer `BaseDataset` y refactorizar `UVLDataset`

1. Añadir `type` a `data_set` con `server_default="uvl"` y `nullable=False`.
2. Renombrar la clase `DataSet` a `BaseDataset`; dejar `DataSet = BaseDataset` como alias.
3. Mover a `BaseDataset` los campos y métodos comunes (C1–C3, C7–C9, C12).
4. Crear `UVLDataset(BaseDataset)` con `polymorphic_identity="uvl"` y mover ahí `feature_models`, `DSMetrics`, `FMMetrics` y los métodos UVL.
5. Mantener `FeatureModel` y `FMMetaData` como están; solo cambia el dueño conceptual.
6. Actualizar repositorios y servicios para usar `BaseDataset` en lo común y `UVLDataset` en lo UVL.
7. Añadir migración con `upgrade` y `downgrade`.
8. Pruebas:
   - los tests actuales de UVL pasan sin cambios;
   - una fila antigua se lee como `UVLDataset`;
   - `BaseDataset.query` devuelve el subtipo correcto;
   - la migración aplica y revierte.

### 7.2. #12 · Crear `WorkflowDataset`

1. Añadir a `data_set` las columnas de workflow: `manifest_json`, `validation_status`, `security_score`, `grade`, `actionlint_version`, `package_format`.
2. Crear `WorkflowDataset(BaseDataset)` con `polymorphic_identity="workflow"`.
3. Crear `WorkflowVersion` con `workflow_dataset_id`, `manifest_json`, `workflow_yaml`, `created_at`.
4. Añadir `workflow_version_id` nullable a `file`, relajar `feature_model_id` a nullable y añadir un `CHECK` de exclusividad: un archivo pertenece a un `FeatureModel` (UVL) o a un `WorkflowVersion`, nunca a ambos.
5. Migración con `upgrade` y `downgrade`; las filas existentes quedan como `uvl`.
6. Pruebas de creación, consulta polimórfica, archivos de ambos tipos y migración.

### 7.3. #13 · Scaffold de la feature `workflow`

1. Crear `app/features/workflow/` con `routes.py`, `services.py`, `repositories.py`, `forms.py`, `templates/` y `assets/`.
2. Registrar la feature en `[tool.splent]`.
3. Rutas vacías que respondan y plantilla base.
4. CI verde.

### 7.4. Después

- **#14** subida de paquetes: formulario y Dropzone por tipo, `.zip` o varios archivos.
- **#15** L1: `ruamel.yaml`, claves duplicadas, números de línea.
- **#16** L2: JSON Schema del manifiesto.
- **#17** extracción de metadatos del workflow.
- **#18** L3/L4 y nota A–F.
- **#19** ciclo de vida y sincronización con fakenodo.
- **#194** búsqueda type-aware.
- **#21** seeds de workflows.

## 8. Riesgos

| Riesgo | Impacto | Mitigación |
| --- | --- | --- |
| La herencia polimórfica rompe consultas existentes | Tests rojos | Alias `DataSet`, pruebas de regresión y migración reversible |
| `ExploreRepository` sigue sesgado a UVL | Workflows invisibles en búsqueda | Refactor S1 antes de la demo de búsqueda |
| `ZenodoService` asume `uvl_filename` | Publicación de workflows falla | Generalizar S4 en #19 |
| `flamapy` se importa desde módulos comunes | Arranque lento y dependencia innecesaria | Import perezoso y revisión de imports |
| Se duplican plantillas y lógica de subida | Deuda UI | Parciales por tipo y helper común |
| `DSMetrics`/`FMMetrics` se muestran como métricas de uso | Datos engañosos | No exponerlas en workflow; moverlas a UVL |
| La migración no revierte | Bloqueo de despliegue | Probar `downgrade` en CI/local antes de fusionar |

## 9. Criterios de aceptación

- Tabla “común vs específico” revisada por el apoyo.
- Decisión de `flamapy` solo UVL registrada en el diario.
- Plan de #11, #12 y #13 aceptado.
- Sin cambios de código en #10.

## 10. Referencias

- `app/features/dataset/models.py`
- `app/features/dataset/services.py`
- `app/features/dataset/forms.py`
- `app/features/dataset/routes.py`
- `app/features/dataset/seeders.py`
- `app/features/dataset/uvl_examples/`
- `app/features/featuremodel/models.py`
- `app/features/hubfile/models.py`
- `app/features/hubfile/services.py`
- `app/features/flamapy/services.py`
- `app/features/flamapy/routes.py`
- `app/features/explore/repositories.py`
- `app/features/explore/templates/explore/index.html`
- `app/features/zenodo/services.py`
- `app/features/dataset/templates/dataset/upload_dataset.html`
- `app/features/dataset/templates/dataset/view_dataset.html`
- `app/features/public/templates/public/index.html`
- `app/templates/base_template.html`
