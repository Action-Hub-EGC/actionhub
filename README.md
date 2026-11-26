# ActionHub

ActionHub es un registro abierto de workflows de GitHub Actions. Cada workflow se publica como un paquete versionado, se valida automáticamente y recibe una calificación de seguridad de A a F antes de descargarlo.

Proyecto de la asignatura **Evolución y Gestión de la Configuración (EGC) 2026/2027**, Grupo 1, Universidad de Sevilla. Es un fork de [UVLHub](https://github.com/EGCETSII/uvlhub) adaptado a un dominio distinto: en lugar de modelos de características UVL, gestiona workflows de GitHub Actions.

## Estado

En desarrollo. **M2 · Producto** cerrado el 23 de noviembre de 2026; siguiente hito: **M3 · Calidad**.

## Enlaces

- [Tablero del proyecto](https://github.com/orgs/Action-Hub-EGC/projects/1)
- [Acta fundacional](docs/acta-fundacional/) · [versión pública sin firmas](docs/acta-fundacional/acta-fundacional-publica.pdf)
- [Diario del equipo](docs/diario/)
- [Decisiones de arquitectura](docs/adr/)
- [fakenodo: Zenodo simulado para desarrollo](fakenodo/README.md)
- [Issues del proyecto](https://github.com/Action-Hub-EGC/actionhub/issues)
- [Documentación de UVLHub](https://docs.uvlhub.io/)

## Arranque rápido

Requisitos: Docker Desktop con Docker Compose.

```bash
cp .env.docker.example .env
docker compose -f docker/docker-compose.dev.yml up --build
```

En Windows (PowerShell), el primer paso es:

```powershell
Copy-Item .env.docker.example .env
```

Abre [http://localhost](http://localhost). La primera vez, el entrypoint aplica las migraciones y siembra la base de datos; puede tardar varios minutos.

Para arrancar sin reconstruir:

```bash
docker compose -f docker/docker-compose.dev.yml up
```

## Comandos útiles

```bash
# Ver logs de la aplicación
docker compose -f docker/docker-compose.dev.yml logs -f web

# Parar el entorno
docker compose -f docker/docker-compose.dev.yml down

# Parar y borrar la base de datos (reset completo)
docker compose -f docker/docker-compose.dev.yml down -v

# Pruebas unitarias y de integración (sin Selenium)
docker compose -f docker/docker-compose.dev.yml exec web \
  pytest app/features/ --ignore-glob='*selenium*'

# Estilo y formato
docker compose -f docker/docker-compose.dev.yml exec web ruff check app rosemary fakenodo
docker compose -f docker/docker-compose.dev.yml exec web black --check app rosemary fakenodo

# Migraciones y datos de ejemplo
docker compose -f docker/docker-compose.dev.yml exec web flask db upgrade
docker compose -f docker/docker-compose.dev.yml exec web rosemary db:seed -y
```

`rosemary db:seed` crea dos usuarios (`user1@example.com` y `user2@example.com`, contraseña `1234`), cuatro datasets UVL y seis workflows de ejemplo con notas de seguridad de la A a la F (ver [formato de paquete](docs/dominio/workflow-package.md#datos-de-ejemplo)).

## Estructura

```text
app/            aplicación Flask
fakenodo/       servicio que simula la API de Zenodo en desarrollo
rosemary/       CLI de generación de features
docker/         compose, imágenes y entrypoints
migrations/     migraciones de Alembic
scripts/        espera de base de datos y utilidades
tests/          pruebas
docs/           documentación del equipo
.github/        CI y plantillas de issues
```

## Ramas

Se usa **EGCFlow**:

- `main`: releases. Solo recibe merges desde `trunk` mediante PR y etiqueta.
- `trunk`: integración. Aquí se fusionan las ramas de tarea.
- `feature/<WI>-<slug>`: una tarea, vida máxima de tres días.
- `hotfix/<slug>`: corrección urgente sobre `main`.

No se crean ramas por persona. Las ramas se actualizan a diario sobre `trunk` y se eliminan al fusionarse. **No se usan pull requests**: la revisión se registra en la issue y la integración es directa tras el CI verde. Los detalles están en [CONTRIBUTING.md](CONTRIBUTING.md).

## Work items

| WI | Issue | Dificultad |
| --- | --- | --- |
| newdataset | [#178](https://github.com/EGCETSII/uvlhub/issues/178) | Común |
| fakenodo | [#177](https://github.com/EGCETSII/uvlhub/issues/177) | Común |
| Versionado mayor | [#196](https://github.com/EGCETSII/uvlhub/issues/196) | Alta |
| Historial de versiones | [#197](https://github.com/EGCETSII/uvlhub/issues/197) | Alta |
| Búsqueda avanzada | [#194](https://github.com/EGCETSII/uvlhub/issues/194) | Media |
| Badge embebible | [#213](https://github.com/EGCETSII/uvlhub/issues/213) | Media |
| Panel de métricas | [#192](https://github.com/EGCETSII/uvlhub/issues/192) | Baja |
| Contador de descargas | [#214](https://github.com/EGCETSII/uvlhub/issues/214) | Baja |

## Equipo

| Persona | Rol |
| --- | --- |
| Marcos Ángel Ayala Blanco | Jefe de Proyecto |
| Rafael de la Rosa Regaña | DevOps |
| Jaime García-Castillejo Carmona | Desarrollador |
| José Fernando Gutiérrez Montero | Desarrollador |
| Francisco Casasola Calzadilla | DevOps |
| Alejandro Ramos Rivera | Desarrollador |

## Licencia

El código hereda la licencia del proyecto original UVLHub. La documentación propia del equipo se publica bajo [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).
