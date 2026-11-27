# Auditoría de registros y métricas de perfil

- **Work item:** WI-192 · issue #61.
- **Rama:** `feature/61-metrics-audit`.
- **Hito:** M2 · Producto.
- **Responsable:** Marcos Ángel Ayala Blanco (@GBK4935).
- **Apoyo:** José Fernando (@Jfgm299).
- **Estado:** propuesta para revisión.

## 1. Propósito

Antes de construir el panel de perfil hay que saber qué datos existen ya, quién los escribe y qué significan. Este documento:

1. inventaría las entidades y los registros de actividad que hereda ActionHub;
2. fija el significado de **borrador** y **publicado**;
3. resuelve la atribución de métricas al propietario del workflow;
4. enumera los problemas de calidad que afectan a las consultas;
5. define las métricas y las consultas que implementará #62.

No se modifica código en #61. El único entregable es este documento y la revisión del apoyo.

## 2. Nomenclatura

ActionHub parte de UVLHub y conserva sus tablas. El dominio cambia, los nombres de las columnas todavía no. Esta tabla fija la equivalencia para que las consultas y la interfaz hablen del dominio correcto.

| UVLHub | ActionHub | Tabla |
| --- | --- | --- |
| `DataSet` | Workflow: ficha del catálogo | `data_set` |
| `DSMetaData` | Metadatos del workflow: título, descripción, DOI, etiquetas | `ds_meta_data` |
| `FeatureModel` | Versión publicada del workflow | `feature_model` |
| `FMMetaData` | Metadatos de la versión: etiqueta, changelog | `fm_meta_data` |
| `Hubfile` | Archivo de la versión: `action.yml`, YAML del workflow, README | `file` |
| `DSDownloadRecord` | Descarga del paquete del workflow | `ds_download_record` |
| `DSViewRecord` | Visita a la ficha del workflow | `ds_view_record` |
| `HubfileDownloadRecord` | Descarga de un archivo suelto | `file_download_record` |
| `HubfileViewRecord` | Vista o previsualización de un archivo | `file_view_record` |
| `DOIMapping` | Redirección de DOI antiguo a DOI nuevo | `doi_mapping` |

El renombrado de tablas y clases queda fuera de #61 y de #62. Se hará, si procede, en una migración posterior con compatibilidad hacia atrás. Las métricas se construyen sobre los nombres actuales.

## 3. Inventario de datos

### 3.1. Catálogo

**`DataSet`** (`app/features/dataset/models.py:67-133`)

| Campo | Tipo | Nulo | Observaciones |
| --- | --- | --- | --- |
| `id` | entero | no | Clave primaria. |
| `user_id` | entero | no | **Propietario del workflow**. Es la única fuente válida para atribuir métricas. |
| `ds_meta_data_id` | entero | no | Metadatos asociados. |
| `created_at` | datetime | no | `datetime.utcnow` por defecto. Sin zona horaria. |

Relaciones: `ds_meta_data` (1:1) y `feature_models` (1:N, borrado en cascada).

**`DSMetaData`** (`app/features/dataset/models.py:53-64`)

| Campo | Tipo | Nulo | Observaciones |
| --- | --- | --- | --- |
| `deposition_id` | entero | sí | Identificador de la deposition en Zenodo. |
| `title` | cadena(120) | no | Título del workflow. |
| `description` | texto | no | Descripción. |
| `publication_type` | enum | no | Heredado; en ActionHub se reinterpreta como tipo de workflow. |
| `publication_doi` | cadena(120) | sí | DOI de la publicación científica asociada, si existe. |
| `dataset_doi` | cadena(120) | sí | **DOI del workflow. Su presencia define `published`.** |
| `tags` | cadena(120) | sí | Etiquetas separadas por comas. |
| `ds_metrics_id` | entero | sí | Métricas estáticas del dataset heredadas. No son métricas de uso. |

**`FeatureModel`** (`app/features/featuremodel/models.py:7-15`)

Representa una versión del workflow. Cuelga de `DataSet` mediante `data_set_id`. Sus archivos cuelgan de `Hubfile` mediante `feature_model_id`.

**`Hubfile`** (`app/features/hubfile/models.py:10-49`)

Archivo de una versión. Campos relevantes: `id`, `name`, `checksum`, `size`, `feature_model_id`. El tamaño y el número de archivos ya se calculan en `DataSet.get_files_count()` y `DataSet.get_file_total_size()`.

**`DOIMapping`** (`app/features/dataset/models.py:163-166`)

Guarda `dataset_doi_old` y `dataset_doi_new`. Solo interviene en redirecciones. No se usa para contar workflows: un workflow con DOI actualizado sigue siendo una fila en `data_set`.

### 3.2. Registros de actividad

Los cuatro registros comparten forma: `id`, `user_id` (nullable), identificador del recurso, fecha y cookie.

| Modelo | Tabla | Recurso | Fecha | Cookie | Escritura |
| --- | --- | --- | --- | --- | --- |
| `DSDownloadRecord` | `ds_download_record` | `dataset_id` | `download_date` | `download_cookie` | `DSDownloadRecordService.record_download` |
| `DSViewRecord` | `ds_view_record` | `dataset_id` | `view_date` | `view_cookie` | `DSViewRecordService.create_new_record` |
| `HubfileDownloadRecord` | `file_download_record` | `file_id` | `download_date` | `download_cookie` | `HubfileDownloadRecordService.record_download` |
| `HubfileViewRecord` | `file_view_record` | `file_id` | `view_date` | `view_cookie` | `HubfileViewRecordService.record_view` |

Reglas de escritura verificadas:

- **`user_id` es el actor, no el propietario.** Si el visitante está autenticado, guarda su id; si es anónimo, `NULL`. El propietario se obtiene siempre por `data_set.user_id` (workflow) o por `file → feature_model → data_set.user_id` (archivo).
- **Deduplicación por cookie.** Cada servicio comprueba si ya existe una fila con la misma terna `(user_id, recurso, cookie)` antes de insertar (`app/features/dataset/services.py:269-281`, `app/features/hubfile/services.py:63-94`). Por tanto, un registro no es una petición HTTP: es una visita o descarga única por navegador y recurso.
- **Anónimos.** Un visitante sin sesión deja `user_id = NULL`, pero conserva cookie. Dos navegadores distintos cuentan dos veces.
- **Fechas.** Las escrituras de los servicios usan `datetime.now(timezone.utc)`. Los `default` de los modelos de dataset usan `datetime.utcnow` (naive). Los modelos de archivo usan `datetime.now(timezone.utc)` (aware). El detalle se trata en §6.2.

### 3.3. Totales globales ya existentes

`app/features/public/routes.py:15-27` calcula los contadores de la portada:

| Función | Consulta |
| --- | --- |
| `count_synchronized_datasets()` | `COUNT(data_set JOIN ds_meta_data WHERE dataset_doi IS NOT NULL)` |
| `count_feature_models()` | `COUNT(feature_model)` |
| `total_dataset_views()` | `COUNT(ds_view_record)` |
| `total_dataset_downloads()` | `COUNT(ds_download_record)` |
| `total_feature_model_views()` | `COUNT(file_view_record)` |
| `total_feature_model_downloads()` | `COUNT(file_download_record)` |

Estos totales son globales y no filtran por propietario ni por estado. Sirven de referencia, pero no se reutilizan directamente en el perfil.

## 4. `summary_for_user` actual

`app/features/profile/services.py:23-30`:

```python
def summary_for_user(self, user_id: int, page: int, per_page: int = 5) -> dict:
    pagination = self._datasets.paginate_for_user(user_id, page, per_page)
    return {
        "datasets": pagination.items,
        "pagination": pagination,
        "total_datasets": self._datasets.count_for_user(user_id),
    }
```

`paginate_for_user` y `count_for_user` (`app/features/dataset/repositories.py:94-102`) filtran por `DataSet.user_id`. Es correcto, pero solo devuelve:

- la página de workflows del usuario;
- el total de workflows, sin distinguir publicados y borradores;
- ninguna métrica de uso.

La plantilla `profile/summary.html` muestra esos datos en una tabla y una línea de “Uploaded datasets”. No hay tarjetas de métricas ni actividad.

**Conclusión:** la atribución de propiedad ya es correcta en la paginación. Lo que falta es agregar los registros de actividad y separar estados.

## 5. Estados: borrador y publicado

### 5.1. Definición

| Estado | Condición | Visible en catálogo público | Ruta de acceso |
| --- | --- | --- | --- |
| **Borrador** (`draft`) | `ds_meta_data.dataset_doi IS NULL` | No | `/dataset/unsynchronized/<id>` solo para el propietario |
| **Publicado** (`published`) | `ds_meta_data.dataset_doi IS NOT NULL` | Sí | `/doi/<dataset_doi>` y ficha pública |

`DataSetRepository.get_synchronized` / `get_unsynchronized` (`app/features/dataset/repositories.py:65-79`) ya implementan exactamente esta partición. `latest_synchronized()` y `count_synchronized_datasets()` usan la misma condición.

**Decisión:** en ActionHub, `synchronized` y `published` son sinónimos; `unsynchronized` y `draft` son sinónimos. La interfaz y la documentación usan **borrador** y **publicado**. Los nombres de los métodos se mantienen hasta que #62 los envuelva, para no romper llamadas existentes.

### 5.2. Validación

La validación L1–L4 y la calificación A–F son **ortogonales** al estado de publicación:

- un borrador puede estar validado y tener buena nota;
- un workflow publicado puede tener una nota baja;
- la nota no se guarda todavía en `DSMetaData` (llega con #12 y #13).

**Propuesta para M2:** publicar exige superar al menos L1 y L2. La comprobación se hará en el servicio de publicación, no en la base de datos, y quedará registrada en un ADR. Hasta que exista esa validación, el estado se deduce solo del DOI. Esta propuesta no bloquea #61 ni #62.

### 5.3. Consecuencias para las métricas

- Un borrador acumula visitas y descargas del propietario. Se cuenta, pero se etiqueta como borrador.
- Las métricas públicas del catálogo solo suman publicados.
- El perfil suma ambos y desglosa. Es la vista del propietario, no la del visitante.

## 6. Calidad de los datos

### 6.1. Atribución de propiedad

**Problema:** `DSDownloadRecord.user_id` y `DSViewRecord.user_id` identifican a quien descarga o visita, no a quien publica.

**Regla:** para métricas de propietario se une siempre:

```text
ds_download_record.dataset_id → data_set.id
ds_view_record.dataset_id     → data_set.id
file_download_record.file_id  → file.id → feature_model.id → data_set.id
file_view_record.file_id      → file.id → feature_model.id → data_set.id
```

y se filtra por `data_set.user_id = :owner_id`.

Desde #12 un archivo también puede colgar de un workflow: `file.workflow_version_id → workflow_version.workflow_dataset_id → data_set.id`. La restricción `ck_file_one_version` garantiza que cada archivo sigue exactamente uno de los dos caminos, así que las métricas suman ambos sin contar dos veces (#91).

**Nunca** se filtra `record.user_id = :owner_id`: eso contaría las descargas que el propietario hace de otros workflows y perdería las visitas anónimas a los suyos.

### 6.2. Zonas horarias

Situación actual:

| Fuente | Escritura | Tipo |
| --- | --- | --- |
| `DataSet.created_at` | `datetime.utcnow` | naive |
| `DSDownloadRecord.download_date` | `datetime.now(timezone.utc)` en servicio; `utcnow` en el modelo | aware al escribir, naive al leer de MariaDB |
| `DSViewRecord.view_date` | `datetime.now(timezone.utc)` en servicio; `utcnow` en el modelo | aware al escribir, naive al leer |
| `Hubfile*.download_date` / `view_date` | `datetime.now(timezone.utc)` | aware al escribir, naive al leer de MariaDB |

MariaDB usa `DATETIME`, que no guarda el desfase. El valor que se persiste es la hora UTC de pared, así que los datos son coherentes entre sí. El riesgo está en Python: comparar un `datetime` leído (naive) con `datetime.now(timezone.utc)` (aware) lanza `TypeError`.

**Decisión:**

1. Todo instante persistido se interpreta como **UTC**.
2. Las consultas de #62 filtran por fechas **en SQL**, no en Python.
3. Al convertir a Python para la plantilla, se usa un helper único:

```python
def as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
```

4. Las escrituras nuevas usan siempre `datetime.now(timezone.utc)`. Corregir los `default` de los modelos es un cambio pequeño y seguro que puede entrar en #62, con su prueba.

### 6.3. Deduplicación y significado del conteo

Los registros no son hits. Son **una fila por cookie, recurso y usuario**. Consecuencias:

- un visitante que vuelve en el mismo navegador no suma otra visita;
- el mismo visitante en otro navegador o en modo incógnito suma otra;
- un usuario autenticado que borra cookies puede sumar de nuevo;
- las descargas repetidas del mismo paquete no inflan el contador.

Por tanto, las métricas se nombran `visits` y `downloads`, no `page_views` ni `requests`. En la interfaz se puede aclarar “visitantes únicos por navegador” cuando se muestre el dato agregado.

**Decisión #66 (22/11/2026):** el contador de descargas muestra **descargas únicas por usuario autenticado o anónimo, navegador y dataset**. Se mantiene `DSDownloadRecord` y su deduplicación por `(user_id, dataset_id, download_cookie)`; #67 reutiliza esos registros y añadirá la etiqueta y el tooltip. La decisión completa está en [`ACTA-2026-08`](../diario/ACTA-2026-08.md).

**Implementación #67:**

- **Servicio único.** `DatasetCounterService` (`app/features/metrics/services.py`) devuelve `{"downloads": n, "views": n}` por dataset. `counts_for_many()` resuelve una lista entera con dos consultas, no dos por dataset.
- **Una sola definición.** Las subconsultas de `DatasetCounterRepository` son también las que usa `MetricsRepository.workflow_metrics()`, así que el perfil y el contador no pueden dar números distintos.
- **Dónde se usa.**
  - La ficha del dataset muestra «views (unique browsers)» y «downloads (unique browsers)», con un tooltip que explica la regla.
  - La ficha del workflow (`/workflow/<id>`) registra la visita igual que la del dataset, con el mismo `DSViewRecord` y la misma cookie, y muestra «visitas · descargas (navegadores únicos)». Las descargas de un workflow seguirán a 0 hasta que tenga ruta de descarga propia: `/dataset/download/<id>` solo sirve datasets UVL.
  - En explore, cada resultado de `POST /explore` lleva `counts`.
  - En la API, cada dataset de `GET /api/v1/datasets/` y `GET /api/v1/datasets/<id>` lleva `counts`.
  - El badge (#213) debe leerlo del mismo servicio.
- **Deduplicación garantizada en la base de datos.** `ds_download_record` y `ds_view_record` tienen una columna generada `user_key = COALESCE(user_id, 0)` y un índice único sobre `(user_key, dataset_id, cookie)`. Esto cierra el riesgo de concurrencia del acta 2026-08.
  - La columna generada hace falta porque MariaDB no trata dos `NULL` como iguales en un índice único, y sin ella los anónimos no quedarían cubiertos.
  - `record_once()` sigue consultando antes de insertar. Si dos peticiones simultáneas insertan la misma fila, la segunda recibe `IntegrityError` y se toma como «ya registrada».
  - La migración `005` borra antes los duplicados existentes y conserva la fila más antigua de cada grupo.
- Las filas con `dataset_id` a `NULL` no cuentan para ningún dataset ni para los totales globales de la portada (`total_dataset_downloads()` y `total_dataset_views()`), así que la suma de las fichas coincide con la portada.

### 6.4. Registros sin recurso vivo

`dataset_id` y `file_id` son nullable, pero las claves foráneas de MariaDB **impiden** borrar un workflow o un archivo que todavía tenga registros: `DataSet.delete()` (`app/features/dataset/models.py:83-85`) falla con `IntegrityError` si hay actividad, porque no existe `ON DELETE CASCADE`. En la práctica no deberían existir huérfanos. Sí pueden existir filas con `dataset_id` o `file_id` a `NULL` si una escritura no valida el recurso.

**Decisión:** las consultas de métricas usan `INNER JOIN` contra la entidad viva. Una fila sin recurso no cuenta. Es el comportamiento correcto para el perfil: no se muestran métricas de workflows que ya no existen. Si en el futuro se añade borrado en cascada o se desactivan las claves foráneas, la regla sigue siendo la misma. Hoy no hace falta una limpieza; si aparecen filas nulas, se corrige el servicio que las creó.

### 6.5. Otros detalles

- `HubfileViewRecord.view_date` y `view_cookie` admiten `NULL` en la migración (`migrations/versions/001.py:159-164`), aunque el servicio siempre los rellena. Las consultas deben tolerar nulos: `COALESCE` o `IS NOT NULL` según el caso.
- `DSDownloadRecord.dataset_id` y `HubfileDownloadRecord.file_id` admiten `NULL`. Se descartan con el `INNER JOIN`.
- `DSMetrics` (`number_of_models`, `number_of_features`) es un residuo estático del dominio UVL. **No se usa** para métricas de uso y no debe mostrarse como si fuera actividad.
- Los totales globales de la portada y las sumas por propietario pueden diferir solo por filas sin `dataset_id`. No es un error.

## 7. Métricas propuestas

Todas se calculan para un `owner_id` y suman borradores y publicados, salvo donde se indique.

### 7.1. Catálogo

| Métrica | Definición | Fuente |
| --- | --- | --- |
| `workflows_total` | Workflows del propietario | `COUNT(data_set)` |
| `published_total` | Workflows con DOI | `COUNT(data_set JOIN ds_meta_data WHERE dataset_doi IS NOT NULL)` |
| `draft_total` | Workflows sin DOI | `workflows_total - published_total` |
| `versions_total` | Versiones de sus workflows | `COUNT(feature_model JOIN data_set)` + `COUNT(workflow_version JOIN data_set)` |
| `files_total` | Archivos de sus versiones | `COUNT(file JOIN feature_model JOIN data_set)` + `COUNT(file JOIN workflow_version JOIN data_set)` |
| `size_total_bytes` | Tamaño agregado de sus archivos | `SUM(file.size)` |

### 7.2. Actividad

| Métrica | Definición | Fuente |
| --- | --- | --- |
| `workflow_views` | Visitas a sus fichas | `COUNT(ds_view_record JOIN data_set)` |
| `workflow_downloads` | Descargas de sus paquetes | `COUNT(ds_download_record JOIN data_set)` |
| `file_views` | Vistas de sus archivos | `COUNT(file_view_record JOIN file JOIN (feature_model o workflow_version) JOIN data_set)` |
| `file_downloads` | Descargas de sus archivos | `COUNT(file_download_record JOIN file JOIN (feature_model o workflow_version) JOIN data_set)` |
| `unique_visitors` | Cookies distintas que han visto alguno de sus workflows | `COUNT(DISTINCT ds_view_record.view_cookie)` |
| `download_rate` | Descargas por visita | `workflow_downloads / workflow_views`, `NULL` si no hay visitas |
| `last_activity_at` | Última visita o descarga, de cualquier tipo | `MAX` de las cuatro fechas |

`versions_total` cuenta las versiones de contenido de cada tipo: `FeatureModel` en UVL y `WorkflowVersion` en workflow (#91). No cuenta filas de `dataset_version` (#36): en UVL una versión del dataset agrupa varios `FeatureModel`, y cambiar ahora la definición alteraría el número de los datasets UVL existentes.

`unique_visitors` cuenta navegadores, no personas. Se etiqueta como “visitantes únicos (por navegador)” en la interfaz.

### 7.3. Por workflow

Para la tabla del perfil y una futura vista de detalle:

| Campo | Definición |
| --- | --- |
| `id`, `title` | Identidad del workflow |
| `published` | `dataset_doi IS NOT NULL` |
| `versions` | Número de `feature_model` |
| `files` | Número de `file` |
| `views` | Visitas a la ficha |
| `downloads` | Descargas del paquete |
| `file_views`, `file_downloads` | Actividad de sus archivos |
| `last_activity_at` | Última actividad del workflow |
| `created_at` | Fecha de alta, normalizada a UTC |

Orden por defecto: `downloads DESC, views DESC, title ASC`. En #62 se puede añadir un límite para el “top 5”.

### 7.4. Serie temporal

Para una gráfica sencilla de los últimos 30 días:

- eje: día UTC;
- series: visitas y descargas del propietario;
- consulta: `GROUP BY DATE(fecha)` en SQL, rellenando los días sin datos con cero en Python.

No se implementa en la primera iteración de #62 si el tiempo aprieta. Es un extra, no un criterio de aceptación.

### 7.5. Lo que no se puede calcular todavía

- **Nota media A–F:** depende de #12 y #13.
- **Validaciones superadas:** depende de #10, #11 y #15.
- **Estrellas o favoritos:** no existe el modelo.
- **Tiempo medio de uso:** no hay eventos de inicio y fin.

Estas métricas no se inventan ni se simulan. Se añadirán cuando exista el dato.

## 8. Contrato propuesto para `summary_for_user`

Se mantienen las claves actuales para no romper la plantilla y se añade `metrics`:

```python
{
    "datasets": [...],            # compatibilidad
    "pagination": pagination,     # compatibilidad
    "total_datasets": 12,         # compatibilidad; igual a metrics.workflows_total
    "metrics": {
        "workflows_total": 12,
        "published_total": 8,
        "draft_total": 4,
        "versions_total": 30,
        "files_total": 47,
        "size_total_bytes": 1048576,
        "workflow_views": 120,
        "workflow_downloads": 54,
        "file_views": 310,
        "file_downloads": 98,
        "unique_visitors": 77,
        "download_rate": 0.45,
        "last_activity_at": datetime(...),  # UTC aware o None
    },
}
```

`metrics` es un diccionario plano para que la plantilla no dependa de objetos. En #62 se decide si conviene un `dataclass` interno; de cara a la vista, el contrato es el diccionario.

## 9. Consultas de referencia para #62

Las consultas se implementarán en un repositorio nuevo, `app/features/metrics/repositories.py`, y se expondrán mediante `MetricsService`. No se meten en `DataSetRepository` para no mezclar catálogo con analítica.

### 9.1. Catálogo del propietario

```python
from sqlalchemy import case, func

catalog = (
    db.session.query(
        func.count(DataSet.id).label("workflows_total"),
        func.coalesce(
            func.sum(case((DSMetaData.dataset_doi.isnot(None), 1), else_=0)), 0
        ).label("published_total"),
        func.coalesce(func.sum(Hubfile.size), 0).label("size_total_bytes"),
    )
    .join(DSMetaData, DataSet.ds_meta_data_id == DSMetaData.id)
    .outerjoin(FeatureModel, FeatureModel.data_set_id == DataSet.id)
    .outerjoin(Hubfile, Hubfile.feature_model_id == FeatureModel.id)
    .filter(DataSet.user_id == owner_id)
    .one()
)
```

Cuidado: al unir versiones y archivos, `COUNT(DataSet.id)` se multiplica. Hay que contar `COUNT(DISTINCT DataSet.id)` o separar la consulta de tamaño. **Recomendación:** dos consultas, una de conteo y otra de tamaño, para que sea legible y no haya sorpresas.

```python
counts = (
    db.session.query(
        func.count(DataSet.id).label("workflows_total"),
        func.coalesce(
            func.sum(case((DSMetaData.dataset_doi.isnot(None), 1), else_=0)), 0
        ).label("published_total"),
    )
    .join(DSMetaData, DataSet.ds_meta_data_id == DSMetaData.id)
    .filter(DataSet.user_id == owner_id)
    .one()
)

versions_files = (
    db.session.query(
        func.count(func.distinct(FeatureModel.id)).label("versions_total"),
        func.count(Hubfile.id).label("files_total"),
        func.coalesce(func.sum(Hubfile.size), 0).label("size_total_bytes"),
    )
    .select_from(DataSet)
    .join(FeatureModel, FeatureModel.data_set_id == DataSet.id)
    .outerjoin(Hubfile, Hubfile.feature_model_id == FeatureModel.id)
    .filter(DataSet.user_id == owner_id)
    .one()
)
```

### 9.2. Actividad del propietario

```python
workflow_views = (
    db.session.query(func.count(DSViewRecord.id))
    .join(DataSet, DSViewRecord.dataset_id == DataSet.id)
    .filter(DataSet.user_id == owner_id)
    .scalar()
)

workflow_downloads = (
    db.session.query(func.count(DSDownloadRecord.id))
    .join(DataSet, DSDownloadRecord.dataset_id == DataSet.id)
    .filter(DataSet.user_id == owner_id)
    .scalar()
)

file_views = (
    db.session.query(func.count(HubfileViewRecord.id))
    .join(Hubfile, HubfileViewRecord.file_id == Hubfile.id)
    .join(FeatureModel, Hubfile.feature_model_id == FeatureModel.id)
    .join(DataSet, FeatureModel.data_set_id == DataSet.id)
    .filter(DataSet.user_id == owner_id)
    .scalar()
)

file_downloads = (
    db.session.query(func.count(HubfileDownloadRecord.id))
    .join(Hubfile, HubfileDownloadRecord.file_id == Hubfile.id)
    .join(FeatureModel, Hubfile.feature_model_id == FeatureModel.id)
    .join(DataSet, FeatureModel.data_set_id == DataSet.id)
    .filter(DataSet.user_id == owner_id)
    .scalar()
)
```

### 9.3. Visitantes únicos

```python
unique_visitors = (
    db.session.query(func.count(func.distinct(DSViewRecord.view_cookie)))
    .join(DataSet, DSViewRecord.dataset_id == DataSet.id)
    .filter(DataSet.user_id == owner_id, DSViewRecord.view_cookie.isnot(None))
    .scalar()
)
```

### 9.4. Por workflow

```python
rows = (
    db.session.query(
        DataSet.id,
        DSMetaData.title,
        DSMetaData.dataset_doi,
        DataSet.created_at,
        func.count(func.distinct(FeatureModel.id)).label("versions"),
        func.count(func.distinct(Hubfile.id)).label("files"),
    )
    .join(DSMetaData, DataSet.ds_meta_data_id == DSMetaData.id)
    .outerjoin(FeatureModel, FeatureModel.data_set_id == DataSet.id)
    .outerjoin(Hubfile, Hubfile.feature_model_id == FeatureModel.id)
    .filter(DataSet.user_id == owner_id)
    .group_by(DataSet.id, DSMetaData.title, DSMetaData.dataset_doi, DataSet.created_at)
    .order_by(DataSet.created_at.desc())
    .all()
)
```

Las visitas y descargas por workflow se obtienen con subconsultas agregadas por `dataset_id` y se unen después. Evita multiplicar filas al mezclar dos tablas de registros.

### 9.5. Última actividad

`GREATEST` no trata los nulos igual en MariaDB y SQLite, y las fechas conviven con filas sin recurso. Es más portable calcular cuatro escalares y quedarse con el mayor en Python:

```python
def _max_date(query) -> datetime | None:
    value = query.scalar()
    return as_utc(value)


candidates = [
    _max_date(
        db.session.query(func.max(DSViewRecord.view_date))
        .join(DataSet, DSViewRecord.dataset_id == DataSet.id)
        .filter(DataSet.user_id == owner_id)
    ),
    _max_date(
        db.session.query(func.max(DSDownloadRecord.download_date))
        .join(DataSet, DSDownloadRecord.dataset_id == DataSet.id)
        .filter(DataSet.user_id == owner_id)
    ),
    _max_date(
        db.session.query(func.max(HubfileViewRecord.view_date))
        .join(Hubfile, HubfileViewRecord.file_id == Hubfile.id)
        .join(FeatureModel, Hubfile.feature_model_id == FeatureModel.id)
        .join(DataSet, FeatureModel.data_set_id == DataSet.id)
        .filter(DataSet.user_id == owner_id)
    ),
    _max_date(
        db.session.query(func.max(HubfileDownloadRecord.download_date))
        .join(Hubfile, HubfileDownloadRecord.file_id == Hubfile.id)
        .join(FeatureModel, Hubfile.feature_model_id == FeatureModel.id)
        .join(DataSet, FeatureModel.data_set_id == DataSet.id)
        .filter(DataSet.user_id == owner_id)
    ),
]

last_activity_at = max((value for value in candidates if value is not None), default=None)
```

## 10. Plan de implementación de #62

1. Crear `app/features/metrics/` con `repositories.py`, `services.py` y `__init__.py`.
2. Implementar `owner_metrics(owner_id)` y `workflow_metrics(owner_id)` con las consultas anteriores.
3. Extender `UserProfileService.summary_for_user` con la clave `metrics`, manteniendo las tres claves actuales.
4. Actualizar `profile/summary.html`: tarjetas de publicados, borradores, versiones, visitas, descargas y última actividad; tabla con estado y métricas por workflow.
5. Añadir pruebas:
   - dos propietarios con workflows publicados y borradores;
   - visitas y descargas anónimas y autenticadas;
   - registros de un workflow ajeno que no deben contar;
   - fila sin recurso que no debe contar;
   - `download_rate` con cero visitas devuelve `None`;
   - fechas normalizadas a UTC.
6. Revisión de José (@Jfgm299) y merge a `trunk`.

**Estimación:** 1 día de implementación y medio de pruebas y revisión. Cabe en M2.

## 11. Decisiones abiertas

| # | Decisión | Propuesta | Quién |
| --- | --- | --- | --- |
| D1 | ¿Publicar exige validación L1+L2? | Sí, a partir de M2, en el servicio de publicación | Equipo |
| D2 | ¿Se renombran las tablas a `workflow`, `version`, `workflow_file`? | No antes de M3; migración con compatibilidad | DevOps |
| D3 | ¿Se añade `ON DELETE CASCADE` para los registros? | No: las claves foráneas actuales protegen la integridad; borrar un workflow con actividad debe ser una decisión explícita | DevOps |
| D4 | ¿La serie temporal de 30 días entra en #62? | Solo si el resto está terminado | Marcos |
| D5 | ¿Se muestra `unique_visitors` en el perfil? | Sí, con la nota “por navegador” | Marcos |

## 12. Revisión

| Revisor | Papel | Fecha | Resultado |
| --- | --- | --- | --- |
| José Fernando (@Jfgm299) | Apoyo del WI-192 | pendiente | pendiente |

Criterio de aceptación de #61: este documento revisado y aprobado por el apoyo, con las decisiones D1–D5 respondidas o aceptadas como pendientes.

## 13. Referencias

- Issue #61: <https://github.com/Action-Hub-EGC/actionhub/issues/61>
- `app/features/dataset/models.py`
- `app/features/dataset/repositories.py`
- `app/features/dataset/services.py`
- `app/features/featuremodel/models.py`
- `app/features/hubfile/models.py`
- `app/features/hubfile/repositories.py`
- `app/features/hubfile/services.py`
- `app/features/profile/services.py`
- `app/features/profile/templates/profile/summary.html`
- `app/features/public/routes.py`
- `migrations/versions/001.py`
