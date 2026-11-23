
# Explorador de Datasets: capacidades actuales y parámetros URL
 
## 1. Análisis de la implementación actual (`explore/repositories.py::filter`)
 
`app/features/explore/repositories.py::ExploreRepository.filter` filtra y ordena los datasets mediante consultas SQLAlchemy.
 
* **Condición base y *joins*:** exige `DSMetaData.dataset_doi.isnot(None)` (solo devuelve datasets con DOI asignado) y ejecuta *inner joins* entre `DataSet`, `DSMetaData`, `Author`, `FeatureModel` y `FMMetaData`. **`DataSet` es un alias de `UVLDataset`: el explorador actual solo devuelve datasets UVL; los `WorkflowDataset` quedan fuera.** Además, los *inner joins* exigen que el dataset tenga al menos un autor y un `FeatureModel`.
  * **Posibles duplicados:** al no haber `distinct()`, un dataset puede aparecer varias veces en el resultado (una por cada combinación autor / *feature model* que cumpla las condiciones). Quien reutilice este filtro debe tenerlo en cuenta.
* **Búsqueda de texto libre (`query`):**
  * Normaliza **únicamente el término de búsqueda** con `unidecode` (minúsculas, sin tildes) y elimina los caracteres `[,.":'()\[\]^;!¡¿?]`. Los datos almacenados no se modifican.
  * Divide la cadena por espacios (`split()`) y aplica condiciones `ILIKE %word%` unidas con `OR` sobre **11 campos**:
    * `DSMetaData`: `title`, `description`, `tags`
    * `Author`: `name`, `affiliation`, `orcid`
    * `FMMetaData`: `uvl_filename`, `title`, `description`, `publication_doi`, `tags`
  * **Búsqueda vacía:** si `query` está vacío, `filters` es una lista vacía y se invoca `or_()` sin argumentos. Con SQLAlchemy 2.0.37 (versión del proyecto) esto está deprecado (emite `SADeprecationWarning`) y **no añade ninguna condición al `WHERE`**, por lo que la consulta devuelve **todos los datasets UVL con DOI que tengan al menos un autor y un `FeatureModel`** (con posibles duplicados por los *joins*). Este caso no está controlado explícitamente en el repositorio; conviene gestionarlo en la ruta o en el repositorio.
  * **Comodines:** la limpieza no elimina `%` ni `_` y el valor se inserta en `ILIKE`; un `query=%` devuelve todo. Habría que sanearlos o documentarlo como comportamiento aceptado.
* **Tipo de publicación (`publication_type`):**
  * Por defecto vale `"any"` (sin filtro).
  * Si recibe otro valor, recorre el enum `PublicationType` comprobando `member.value.lower() == publication_type` (el valor debe llegar **en minúsculas**) y filtra por `DSMetaData.publication_type == matching_type.name`.
  * **Valor desconocido:** si no coincide con ningún miembro del enum, el filtro **se ignora silenciosamente** (equivale a `"any"`); no se produce error.
* **Etiquetas (`tags`):**
  * Recibe una lista de cadenas (`[]` por defecto). Si no está vacía, filtra con `OR` usando `DSMetaData.tags.ilike(f"%{tag}%")`.
  * A diferencia de `query`, solo evalúa las etiquetas del dataset (no las de `FMMetaData`).
  * Los valores **no se normalizan** (ni `unidecode` ni limpieza) y se insertan tal cual en el patrón `ILIKE`, por lo que `%` y `_` actuarían como comodines.
* **Ordenación (`sorting`):**
  * Ordena exclusivamente por `DataSet.created_at`: ascendente si `sorting == "oldest"` y descendente en cualquier otro caso (por defecto `"newest"`).


### Uso de `DSMetrics`
 
* **No interviene en el filtrado ni en la ordenación:** `ExploreRepository.filter` no hace `join` con `ds_metrics` ni usa sus campos, y `DataSet.to_dict()` tampoco los serializa en la respuesta JSON.
* **Consideración para futuros filtros:** en `app/features/dataset/models.py`, la relación `DSMetaData.ds_metrics` (1:1 mediante `ds_metrics_id`) apunta a `DSMetrics`, cuyos campos `number_of_models` y `number_of_features` son `db.String(120)` (texto, no enteros). Para filtrar u ordenar por ellos habrá que añadir `.join(DSMetaData.ds_metrics)` y hacer un *cast* numérico en la consulta.


---
 
## 2. Parámetros de consulta en la URL (propuesta)
 
Estado actual (`app/features/explore/routes.py`): `GET /explore` solo lee el parámetro `query` (`request.args.get("query", "")`); el filtrado completo se ejecuta vía `POST /explore` con *payload* JSON.
 
Para que cualquier búsqueda filtrada sea compartible mediante enlace directo (`GET /explore?...`), se definen los siguientes parámetros canónicos. **Todos salvo `query` son una propuesta aún no implementada.**
 
| Parámetro | Tipo | Valor por defecto | Valores admitidos / formato | Descripción | Ejemplo |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `query` | `string` | `""` | Texto libre | Términos de búsqueda evaluados (`OR`, insensible a mayúsculas y tildes) sobre metadatos del dataset, autores y *feature models*. | `?query=smart+home` |
| `publication_type` | `string` | `"any"` | `"any"` o cualquier `.value` del enum `PublicationType`, **en minúsculas**: `none`, `annotationcollection`, `book`, `section`, `conferencepaper`, `datamanagementplan`, `article`, `patent`, `preprint`, `deliverable`, `milestone`, `proposal`, `report`, `softwaredocumentation`, `taxonomictreatment`, `technicalnote`, `thesis`, `workingpaper`, `other` | Filtra por tipo de publicación. `"any"` no filtra. Un valor no reconocido se ignora (equivale a `"any"`). La fuente de verdad de los valores es el enum `PublicationType`. | `?publication_type=article` |
| `author` | `string` | `""` | Texto libre | Filtra por `Author.name`, `Author.affiliation` o `Author.orcid` (`OR`, insensible a mayúsculas). | `?author=alice` |
| `start_date` | `string` | `""` | Fecha ISO `YYYY-MM-DD` | Filtra `DataSet.created_at >= start_date`. | `?start_date=2024-01-01` |
| `end_date` | `string` | `""` | Fecha ISO `YYYY-MM-DD` | Filtra `DataSet.created_at <= end_date` (incluye el día completo). | `?end_date=2024-12-31` |
| `tags` | `list[string]` | `[]` | Lista separada por comas: `tag1,tag2` | Filtra datasets cuyas etiquetas en `DSMetaData.tags` coincidan con alguna de las indicadas (`OR`, insensible a mayúsculas). El parseo (`split(",")`, recorte de espacios y descarte de vacíos) debe hacerlo la ruta. | `?tags=automotive,iot` |
| `sorting` | `string` | `"newest"` | `"newest"`, `"oldest"` | Ordena por fecha de creación (`DataSet.created_at`): más recientes primero (`newest`) o más antiguos primero (`oldest`). Cualquier otro valor se trata como `newest`. | `?sorting=oldest` |
 
### Ejemplo de URL compartible
 
```text
/explore?query=spl&publication_type=article&author=alice&start_date=2024-01-01&tags=variability,uvl&sorting=newest
```
 
---
 
## 3. Alcance
 
Las decisiones de alcance de esta tarea (filtro por comunidades, [EGCETSII/uvlhub#210](https://github.com/EGCETSII/uvlhub/issues/210), e integración de Elasticsearch, [EGCETSII/uvlhub#204](https://github.com/EGCETSII/uvlhub/issues/204), fuera de alcance) están registradas en [ACTA 2026-07](../diario/ACTA-2026-07.md).