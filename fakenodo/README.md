# fakenodo

Servicio HTTP que simula la parte de la API de depósitos de Zenodo que usa ActionHub. Sirve para desarrollar y probar la integración con Zenodo sin token y sin depender del sandbox. No es una réplica completa de Zenodo.

- Work item: [#3](https://github.com/Action-Hub-EGC/actionhub/issues/3), basado en [EGCETSII/uvlhub#177](https://github.com/EGCETSII/uvlhub/issues/177).
- Contrato que debe cumplir: [auditoría de llamadas a Zenodo](../docs/zenodo-api-audit.md).

## Puesta en marcha

Requisito: el entorno de desarrollo del [README](../README.md#arranque-rápido). fakenodo es un servicio más de `docker/docker-compose.dev.yml`.

1. Crea el `.env` si aún no existe: `cp .env.docker.example .env` (en PowerShell, `Copy-Item .env.docker.example .env`).
2. Añade al `.env` la URL de fakenodo:

   ```dotenv
   ZENODO_API_URL=http://fakenodo:8000/api/deposit/depositions
   ```

3. Arranca el entorno: `docker compose -f docker/docker-compose.dev.yml up -d --build`.
4. Comprueba que `web` llega a fakenodo. Debe responder `{"status":"ok"}`:

   ```bash
   docker compose -f docker/docker-compose.dev.yml exec web curl -s http://fakenodo:8000/health
   ```

El puerto 8000 solo está abierto dentro de la red de Compose, no en el host. Por eso la comprobación se hace desde `web`.

## Cambiar entre Zenodo y fakenodo

`ZENODO_API_URL` es la única variable que decide adónde llama ActionHub (`ZenodoService.get_zenodo_url()`):

| `ZENODO_API_URL` | Destino |
| --- | --- |
| `http://fakenodo:8000/api/deposit/depositions` | fakenodo |
| Sin definir, con `FLASK_ENV=production` | `https://zenodo.org/api/deposit/depositions` |
| Sin definir, en cualquier otro entorno | `https://sandbox.zenodo.org/api/deposit/depositions` |

Para volver a Zenodo, borra o comenta la línea del `.env` y recrea `web`:

```bash
docker compose -f docker/docker-compose.dev.yml up -d web
```

No uses `docker compose restart`: el contenedor conserva las variables del `.env` con las que se creó. Contra Zenodo o su sandbox hace falta además `ZENODO_ACCESS_TOKEN`. fakenodo no lo necesita.

## Qué implementa hoy

| Método | Ruta | Estado |
| --- | --- | --- |
| `GET` | `/health` | Disponible |
| `POST` | `/api/deposit/depositions` | Disponible: crea una deposition `unsubmitted` (`201`) |
| `GET` | `/api/deposit/depositions` | Disponible (`200`) |
| `GET` | `/api/deposit/depositions/{id}` | Disponible (`200` o `404`) |
| `PUT` | `/api/deposit/depositions/{id}` | Disponible: cambia solo `metadata`, sin tocar el DOI (`200`, `400` o `404`) |
| `DELETE` | `/api/deposit/depositions/{id}` | Disponible (`204` o `404`) |
| `POST` | `/api/deposit/depositions/{id}/files` | Disponible: añade un archivo a una deposition `unsubmitted` (`201`, `400` o `404`) |
| `DELETE` | `/api/deposit/depositions/{id}/files/{file_id}` | Disponible: quita un archivo de una deposition `unsubmitted` (`204`, `400` o `404`) |
| `POST` | `/api/deposit/depositions/{id}/actions/publish` | Disponible: pasa la deposition a `done` y le asigna DOI (`202`, `400` o `404`) |
| `POST` | `/api/deposit/depositions/{id}/actions/newversion` | Disponible: crea el borrador de la versión siguiente (`201`, `400` o `404`) |

Al publicar, fakenodo asigna `doi` = `10.5072/fakenodo.<id>`, único porque lo es el `id`, y aparece después en `GET /api/deposit/depositions/{id}`. En la primera publicación de un concepto fija también `conceptdoi` = `10.5072/fakenodo.concept.<conceptrecid>`; si la deposition ya lo tiene, lo conserva. Como Zenodo, rechaza con `400` publicar una deposition sin archivos (`Minimum one file must be provided.`) o ya publicada.

### Versiones

Todas las versiones de un dataset comparten `conceptrecid` y `conceptdoi`; cada una tiene su propio `id` y su propio `doi`.

1. `POST /{id}/actions/newversion` sobre una deposition publicada crea un borrador `unsubmitted` con el mismo `conceptrecid` y `conceptdoi`, sin `doi`, con `version` siguiente y con los metadatos y archivos de la última versión publicada. Como en Zenodo, la respuesta es la deposition sobre la que se llamó, y el borrador está en `links.latest_draft`.
2. Se cambian los archivos del borrador con `POST /{id}/files` y `DELETE /{id}/files/{file_id}`, y los metadatos con `PUT /{id}`.
3. `POST /{id}/actions/publish` le asigna un DOI nuevo y conserva el `conceptdoi`. Como Zenodo, responde `400` si sus archivos son los mismos que los de una versión ya publicada (`New version's files must differ from all previous versions.`).

Cambiar solo los metadatos con `PUT /{id}` mantiene el mismo DOI; no crea versión. Un concepto tiene como mucho un borrador: si se vuelve a llamar a `newversion` mientras existe, se devuelve el mismo.

## Qué no replica

fakenodo cubre solo lo que ActionHub consume. A diferencia de Zenodo:

- **No autentica.** Ignora `access_token`; cualquier petición se acepta.
- **No valida metadatos.** Acepta cualquier objeto en `metadata`; Zenodo responde `400` si un campo no es válido (por ejemplo, un `upload_type` desconocido) y no deja publicar sin los obligatorios.
- **No registra DOI reales.** Los DOI que asigne usarán el prefijo de pruebas de DataCite (`10.5072`), que no resuelve en doi.org.
- **Respuestas reducidas.** Una deposition solo tiene `id`, `conceptrecid`, `conceptdoi`, `doi`, `state`, `metadata`, `files` y `version`; no incluye `links` (salvo `links.latest_draft` en la respuesta de `newversion`), `created`, `modified`, `record_id` ni `doi_url`. Los errores son `{"message": ...}`, sin la lista `errors` de Zenodo.
- **Listado sin filtros.** `GET /api/deposit/depositions` devuelve todas las depositions; ignora `q`, `status`, `sort`, `page` y `size`.
- **Edición sin `actions/edit`.** `PUT /{id}` cambia los metadatos de una deposition publicada directamente; Zenodo exige antes `POST /{id}/actions/edit` y después volver a publicar. En ambos casos el DOI no cambia.
- **Borrado sin restricciones.** Borra cualquier deposition; Zenodo solo permite borrar las no publicadas.
- **Solo la API de depósitos.** No hay `/api/records`, búsqueda, comunidades, OAI-PMH ni interfaz web.
- **Sin límites.** No hay cuotas, tamaño máximo de archivo ni límite de peticiones.
- **Solo para desarrollo.** Usa el servidor de desarrollo de Flask y no está en los compose de producción.

## Datos y configuración

| Variable | Valor en la imagen | Uso |
| --- | --- | --- |
| `FAKENODO_STORE_PATH` | `/data/fakenodo.sqlite3` | Fichero SQLite de las depositions |
| `PORT` | `8000` | Puerto de escucha |

`/data` es el volumen `uvlhub_fakenodo_data`, así que las depositions sobreviven a `docker compose down`. Para empezar de cero sin tocar la base de datos de ActionHub:

```bash
docker compose -f docker/docker-compose.dev.yml rm -sf fakenodo
docker volume rm uvlhub_fakenodo_data
```

`docker compose down -v` también lo borra, pero se lleva con él la base de datos de ActionHub (`db_data`).

## Pruebas y CI
Los tests de `fakenodo` están en `app/features/zenodo/tests/`:
- `test_fakenodo.py` y `test_store.py`: pruebas unitarias y de API HTTP (no necesitan base de datos).
- `test_fakenodo_contract.py`: pruebas de contrato que ejecutan `ZenodoService` contra un servidor HTTP real de `fakenodo`.
```bash
docker compose -f docker/docker-compose.dev.yml exec web \
  pytest -v app/features/zenodo/tests/test_fakenodo.py app/features/zenodo/tests/test_store.py app/features/zenodo/tests/test_fakenodo_contract.py
```
En `.github/workflows/CI_pipeline.yml`:
- `lint` pasa ruff y black sobre `fakenodo/`.
- `test` ejecuta sus tests y mide su cobertura (`--cov=fakenodo`).
- `fakenodo` construye la imagen, la arranca y prueba crear, consultar, listar, subir un archivo, publicar, crear y publicar una versión nueva y borrar una deposition, también después de recrear el contenedor sobre el mismo volumen.