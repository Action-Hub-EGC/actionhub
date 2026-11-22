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
| `DELETE` | `/api/deposit/depositions/{id}` | Disponible (`204` o `404`) |
| `POST` | `/api/deposit/depositions/{id}/files` | Pendiente: [#28](https://github.com/Action-Hub-EGC/actionhub/issues/28) |
| `POST` | `/api/deposit/depositions/{id}/actions/publish` | Pendiente: [#29](https://github.com/Action-Hub-EGC/actionhub/issues/29) |
| `POST` | `/api/deposit/depositions/{id}/actions/newversion` | Pendiente: [#30](https://github.com/Action-Hub-EGC/actionhub/issues/30) |

Mientras #28 y #29 sigan abiertas, subir un dataset contra fakenodo crea la deposition, pero termina en estado parcial: el envío de archivos responde `404` y el dataset se queda sin DOI. Quien cierre cada una de esas tareas actualiza esta tabla.

## Qué no replica

fakenodo cubre solo lo que ActionHub consume. A diferencia de Zenodo:

- **No autentica.** Ignora `access_token`; cualquier petición se acepta.
- **No valida metadatos.** Acepta cualquier objeto en `metadata`; Zenodo responde `400` si un campo no es válido (por ejemplo, un `upload_type` desconocido) y no deja publicar sin los obligatorios.
- **No registra DOI reales.** Los DOI que asigne usarán el prefijo de pruebas de DataCite (`10.5072`), que no resuelve en doi.org.
- **Respuestas reducidas.** Una deposition solo tiene `id`, `conceptrecid`, `doi`, `state`, `metadata`, `files` y `version`; no incluye `links`, `created`, `modified`, `record_id` ni `doi_url`. Los errores son `{"message": ...}`, sin la lista `errors` de Zenodo.
- **Listado sin filtros.** `GET /api/deposit/depositions` devuelve todas las depositions; ignora `q`, `status`, `sort`, `page` y `size`.
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

Los tests unitarios están en `app/features/zenodo/tests/` (`test_fakenodo.py` y `test_store.py`) y no necesitan base de datos:

```bash
docker compose -f docker/docker-compose.dev.yml exec web \
  pytest app/features/zenodo/tests/test_fakenodo.py app/features/zenodo/tests/test_store.py
```

En `.github/workflows/CI_pipeline.yml`:

- `lint` pasa ruff y black sobre `fakenodo/`.
- `test` ejecuta sus tests y mide su cobertura (`--cov=fakenodo`).
- `fakenodo` construye la imagen, la arranca y prueba crear, consultar, listar y borrar una deposition, también después de recrear el contenedor sobre el mismo volumen.
