# Auditoria de llamadas a Zenodo

## Alcance

Este documento describe las llamadas realizadas por
`app/features/zenodo/services.py`. El objetivo es indicar el contrato minimo
que necesita implementar fakenodo.

## Composicion de la URL base

`ZenodoService.get_zenodo_url()` usa estas reglas:

1. Si `FLASK_ENV == "production"`, la URL por defecto es
   `https://zenodo.org/api/deposit/depositions`.
2. En desarrollo, staging o cualquier otro entorno distinto de produccion,
   la URL por defecto es
   `https://sandbox.zenodo.org/api/deposit/depositions`.
3. Si existe `ZENODO_API_URL`, su valor sustituye por completo la URL por
   defecto.

En todos los casos, la URL de coleccion configurada se considera la raiz
`/api/deposit/depositions`. Los identificadores se anaden al final sin otro
procesado:

* `{base}/{deposition_id}/files`
* `{base}/{deposition_id}/actions/publish`
* `{base}/{deposition_id}`

Las llamadas envian `access_token` como query parameter:
`{"access_token": ZENODO_ACCESS_TOKEN}`. Las llamadas con JSON usan el header
`Content-Type: application/json`.

## Tabla de llamadas

| Metodo | Ruta relativa | Payload / parametros | Respuesta esperada | Campos usados por ActionHub |
|---|---|---|---|---|
| `GET` | `/api/deposit/depositions` | Query: `access_token`; header JSON | `200` con la lista de depositions | Ninguno en `test_connection`; `get_all_depositions()` devuelve el JSON completo. Ningun consumidor usa campos concretos actualmente. |
| `POST` | `/api/deposit/depositions` | Query: `access_token`; header JSON; body `{metadata: {...}}` con title, upload_type, description, creators y, segun el caso, publication_type, keywords, access_right y license | `201` con el deposition creado | `id` para construir rutas y guardarlo; `conceptrecid` para confirmar que se puede continuar el flujo. |
| `POST` | `/api/deposit/depositions/{id}/files` | Query: `access_token`; multipart/form-data; campo `name` y archivo binario `file` | `201` con informacion del archivo | Ninguno en el flujo actual; el metodo devuelve el JSON completo. |
| `POST` | `/api/deposit/depositions/{id}/actions/publish` | Query: `access_token`; header JSON; sin body | `202` con el deposition publicado | Ninguno en el flujo actual; el metodo devuelve el JSON completo. |
| `GET` | `/api/deposit/depositions/{id}` | Query: `access_token`; header JSON | `200` con el deposition | `doi` cuando se llama desde `get_doi()`; `get_deposition()` devuelve el JSON completo. |
| `DELETE` | `/api/deposit/depositions/{id}` | Query: `access_token`; sin header ni body | `204` | Ninguno; solo se valida el codigo de estado. |

## Payload de creacion de una deposition real

Los metadatos enviados por `create_new_deposition()` son:

* `title`
* `upload_type`: `dataset` o `publication`
* `publication_type`: solo si el tipo no es `none`
* `description`
* `creators`: `name`, y opcionalmente `affiliation` y `orcid`
* `keywords`: los tags separados por `, ` mas `uvlhub`
* `access_right`: siempre `open`
* `license`: siempre `CC-BY-4.0`

El probe de `/zenodo/test` usa un payload mas pequeño:

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

Despues crea el archivo `test_file.txt`, lo elimina mediante el endpoint
de deposicion y usa el campo de respuesta `id` entre esas operaciones.

## Códigos de estado que ActionHub exige

* Coleccion: `GET 200`, `POST 201`
* Archivo: `POST 201`
* Publicacion: `POST 202`
* Deposition individual: `GET 200`
* Eliminacion: `DELETE 204`

Cualquier otro estado se trata como error. Los endpoints de fallo pueden
devolver JSON con un campo `message`; los metodos de creacion y subida incluyen
el JSON completo en el mensaje de excepcion.

