# Auditoría de llamadas a Zenodo

- **Issue:** #24 · WI #177 (fakenodo).
- **Fecha:** 17 de noviembre de 2026.
- **Fuente:** `app/features/zenodo/services.py`.

## Alcance

Este documento describe las llamadas que ActionHub realiza a Zenodo. El objetivo es fijar el contrato mínimo que debe implementar fakenodo: rutas, métodos, payloads, códigos de estado y campos de respuesta que ActionHub consume.

## Composición de la URL base

`ZenodoService.get_zenodo_url()` aplica estas reglas:

1. Si `FLASK_ENV == "production"`, la URL por defecto es `https://zenodo.org/api/deposit/depositions`.
2. En desarrollo, staging o cualquier entorno distinto de producción, la URL por defecto es `https://sandbox.zenodo.org/api/deposit/depositions`.
3. Si existe `ZENODO_API_URL`, su valor sustituye por completo la URL por defecto.

En todos los casos, la URL configurada se considera la raíz de la colección `/api/deposit/depositions`. Los identificadores se añaden al final sin otro procesado:

- `{base}/{deposition_id}/files`
- `{base}/{deposition_id}/actions/publish`
- `{base}/{deposition_id}`

Las llamadas envían `access_token` como parámetro de consulta: `{"access_token": ZENODO_ACCESS_TOKEN}`. Las llamadas con JSON usan la cabecera `Content-Type: application/json`.

### Enlaces al registro desde el navegador (#32)

La URL de la API no sirve para el navegador cuando apunta a un contenedor (`http://fakenodo:8000`). `app/features/zenodo/urls.py` construye el enlace público del registro:

1. `ZENODO_RECORD_URL` (configuración o entorno) es la base explícita.
2. Sin ella, se deriva de `ZENODO_API_URL`: `zenodo.org` y `sandbox.zenodo.org` usan su página `/records`; cualquier otro host se enlaza tal cual, de modo que fakenodo enlaza a fakenodo.
3. Sin `ZENODO_API_URL`, se aplica la misma URL por defecto que `ZenodoService`.

El enlace final es `{base}/{deposition_id}` y solo se muestra para un dataset publicado con deposition.

## Tabla de llamadas

| Método | Ruta relativa | Payload o parámetros | Respuesta esperada | Campos usados por ActionHub |
|---|---|---|---|---|
| `GET` | `/api/deposit/depositions` | Consulta: `access_token`; cabecera JSON | `200` con la lista de depositions | Ninguno en `test_connection`; `get_all_depositions()` devuelve el JSON completo. Ningún consumidor usa campos concretos actualmente. |
| `POST` | `/api/deposit/depositions` | Consulta: `access_token`; cabecera JSON; cuerpo `{metadata: {...}}` con `title`, `upload_type`, `description`, `creators` y, según el caso, `publication_type`, `keywords`, `access_right` y `license` | `201` con la deposition creada | `id` para construir rutas y guardarlo; `conceptrecid` para confirmar que se puede continuar el flujo. |
| `POST` | `/api/deposit/depositions/{id}/files` | Consulta: `access_token`; `multipart/form-data`; campo `name` y archivo binario `file` | `201` con información del archivo | Ninguno en el flujo actual; el método devuelve el JSON completo. |
| `POST` | `/api/deposit/depositions/{id}/actions/publish` | Consulta: `access_token`; cabecera JSON; sin cuerpo | `202` con la deposition publicada | Ninguno en el flujo actual; el método devuelve el JSON completo. |
| `GET` | `/api/deposit/depositions/{id}` | Consulta: `access_token`; cabecera JSON | `200` con la deposition | `doi` cuando se llama desde `get_doi()`; `get_deposition()` devuelve el JSON completo. |
| `DELETE` | `/api/deposit/depositions/{id}` | Consulta: `access_token`; sin cabecera ni cuerpo | `204` | Ninguno; solo se valida el código de estado. |

## Payload de creación de una deposition real

Los metadatos enviados por `create_new_deposition()` son:

- `title`.
- `upload_type`: `dataset` o `publication`.
- `publication_type`: solo si el tipo no es `none`.
- `description`.
- `creators`: `name`, y opcionalmente `affiliation` y `orcid`.
- `keywords`: los tags separados por `, ` más `uvlhub`.
- `access_right`: siempre `open`.
- `license`: siempre `CC-BY-4.0`.

El probe de `/zenodo/test` usa un payload más pequeño:

```json
{
  "metadata": {
    "title": "Test Deposition",
    "upload_type": "dataset",
    "description": "This is a test deposition created via Zenodo API",
    "creators": [{"name": "John Doe"}]
  }
}
```

Después crea el archivo `test_file.txt`, lo elimina mediante el endpoint de deposition y usa el campo de respuesta `id` entre esas operaciones.

## Códigos de estado que ActionHub exige

- Colección: `GET 200`, `POST 201`.
- Archivo: `POST 201`.
- Publicación: `POST 202`.
- Deposition individual: `GET 200`.
- Eliminación: `DELETE 204`.

Cualquier otro estado se trata como error. Los endpoints de fallo pueden devolver JSON con un campo `message`; los métodos de creación y subida incluyen el JSON completo en el mensaje de excepción.
