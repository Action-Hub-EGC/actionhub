# Tipos de dataset y bloques de la página común

- **Issues:** #20 (bloques y explorador) y #23 (documentación).
- **Fecha:** 24 de noviembre de 2026.
- **Estado:** implementado en `trunk`.

## 1. Modelo común y tipos concretos

ActionHub comparte una identidad de dataset para el catálogo, las métricas, el
explorador y los contadores. El tipo concreto solo añade el contenido que le es
propio:

| Pieza | UVL | Workflow |
| --- | --- | --- |
| Fila del catálogo | `BaseDataset` con `type='uvl'` | `BaseDataset` con `type='workflow'` |
| Clase | `UVLDataset` | `WorkflowDataset` |
| Metadatos comunes | `DSMetaData`, `Author`, `DSMetrics` | Igual |
| Versión | `DatasetVersion` | `DatasetVersion` |
| Contenido de la versión | `FeatureModel` → `Hubfile` | `WorkflowVersion` → `Hubfile` |
| Bloque de la página | `dataset/blocks/uvl.html` | `workflow/blocks/workflow.html` |

La tabla física sigue siendo `data_set`; el discriminador `type` decide qué
clase construye SQLAlchemy. `BaseDataset` ofrece lo que necesitan todos los
tipos: versiones, archivos, DOI público, contadores y serialización.

## 2. Página común y registro de bloques

`dataset/view_dataset.html` no conoce ningún tipo concreto. Recorre los bloques
registrados para el tipo del dataset:

```jinja
{% for block in blocks %}
    {% include block %}
{% endfor %}
```

El registro vive en `app/features/dataset/blocks.py`. Cada feature declara su
bloque en `init_feature`:

```python
register_dataset_block("uvl", "dataset/blocks/uvl.html")
register_dataset_block("workflow", "workflow/blocks/workflow.html")
```

El bloque recibe el dataset en el contexto y puede usar sus relaciones
específicas (`dataset.feature_models` o `dataset.versions`). La página común
mantiene título, autores, DOI, etiquetas, enlace a Zenodo, descarga y
contadores; el bloque añade lo que solo tiene sentido para ese tipo.

### Añadir un tipo nuevo

1. Crear el modelo y su discriminador en `BaseDataset`.
2. Añadir su contenido de versión (`DatasetVersion` ya es común).
3. Implementar `files()` o la relación de archivos que use el tipo.
4. Crear `app/features/<tipo>/templates/<tipo>/blocks/<tipo>.html`.
5. En `init_feature`, llamar a `register_dataset_block("<tipo>", "<ruta>")`.
6. Añadir el tipo a `DATASET_TYPES` del explorador si debe poder filtrarse.

No hay que editar `view_dataset.html`: si no hay bloque registrado, la página
muestra un aviso neutro. Los `url_for` de features opcionales se protegen con
`endpoint_registered`, de modo que un entorno sin `flamapy` siga renderizando
la página UVL sin los enlaces de exportación.

## 3. Explorador

`ExploreRepository` consulta `BaseDataset`, no `UVLDataset`. Los joins a
`Author`, `FeatureModel`, `FMMetaData` y `WorkflowVersion` son **outer joins**:
un dataset publicado sin modelo de características sigue siendo visible, y un
workflow no desaparece por no tener `FeatureModel`. El parámetro
`dataset_type` (`any`, `uvl`, `workflow`) filtra por el discriminador y se
conserva en la URL junto con el resto de filtros.

La búsqueda de texto cubre metadatos comunes, autores, campos de UVL y el YAML
y el manifiesto de workflow. Los resultados se deduplican porque un dataset
puede tener varios autores o versiones.

## 4. Formato de paquete de workflow

El formato completo está en [`workflow-package.md`](workflow-package.md). En
resumen:

- ZIP con `actionhub.yaml`, `workflow.yml` y los archivos de apoyo.
- `actionhub.yaml` declara nombre, descripción, versión SemVer, autores,
  licencia y etiquetas.
- La validación de estructura y manifiesto ocurre antes de escribir en la base
  de datos.
- El paquete se guarda como una `WorkflowVersion` dentro de la versión 1 del
  dataset, con los archivos en `uploads/.../dataset_<id>/v1/`.

## 5. Validación L1–L4

| Capa | Estado | Qué cubre |
| --- | --- | --- |
| L1 | Implementada y bloqueante | Sintaxis y estructura del workflow. |
| L2 | Implementada y bloqueante | Esquema del manifiesto y del workflow. |
| L3 | Planificada (#18) | Comprobaciones estáticas adicionales. |
| L4 | Planificada (#18) | Reglas de seguridad y calificación A–F. |

Hoy un workflow pasa a `validated` solo después de L1 y L2. La calificación
A–F se guarda en `WorkflowDataset.grade` cuando L4 la calcule; la página común
ya muestra la insignia si existe. La documentación no presenta L3/L4 como
terminadas.

## 6. `flamapy` se mantiene para UVL

`flamapy` sigue siendo la librería de análisis de modelos UVL. No se elimina ni
se hace obligatoria para los workflows:

- La feature `flamapy` conserva sus rutas de validación, exportación y
  comprobación sintáctica para UVL.
- El bloque UVL oculta los enlaces de exportación si la feature no está
  cargada (`endpoint_registered`).
- El tipo workflow no importa `flamapy`: su validación es L1/L2 y su contenido
  es un paquete de GitHub Actions.

Mantener `flamapy` evita romper el catálogo UVL heredado y permite comparar
ambos tipos en el mismo producto sin duplicar la plataforma.
