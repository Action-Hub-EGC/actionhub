# ActionHub

ActionHub es un registro abierto de workflows de GitHub Actions. Cada workflow se publica como un paquete versionado, se valida automáticamente y recibe una calificación de seguridad de A a F antes de descargarlo.

Proyecto de la asignatura **Evolución y Gestión de la Configuración (EGC) 2026/2027**, Grupo 1, Universidad de Sevilla. Es un fork de [UVLHub](https://github.com/EGCETSII/uvlhub) adaptado a un dominio distinto: en lugar de modelos de características UVL, gestiona workflows de GitHub Actions.

## Estado

En desarrollo. Hito actual: **M1 · Dominio** (18 de noviembre de 2026).

## Enlaces

- [Tablero del proyecto](https://github.com/orgs/Action-Hub-EGC/projects/1)
- [Acta fundacional](docs/acta-fundacional/)
- [Diario del equipo](docs/diario/)
- [Decisiones de arquitectura](docs/adr/)
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
docker compose -f docker/docker-compose.dev.yml exec web flake8 app rosemary fakenodo
docker compose -f docker/docker-compose.dev.yml exec web black --check app rosemary fakenodo
docker compose -f docker/docker-compose.dev.yml exec web isort --check-only app rosemary fakenodo

# Migraciones y datos de ejemplo
docker compose -f docker/docker-compose.dev.yml exec web flask db upgrade
docker compose -f docker/docker-compose.dev.yml exec web rosemary db:seed -y
```

## Estructura

```text
app/            aplicación Flask
rosemary/       CLI de generación de features
docker/         compose, imágenes y entrypoints
migrations/     migraciones de Alembic
scripts/        espera de base de datos y utilidades
tests/          pruebas
docs/           documentación del equipo
.github/        CI y plantillas de issues y PR
```

## Ramas

Se usa **EGCFlow**:

- `main`: releases. Solo recibe merges desde `trunk` mediante PR y etiqueta.
- `trunk`: integración. Aquí se fusionan las ramas de tarea.
- `feature/<WI>-<slug>`: una tarea, vida máxima de tres días.
- `hotfix/<slug>`: corrección urgente sobre `main`.

No se crean ramas por persona. Las ramas se actualizan a diario sobre `trunk` y se eliminan al fusionarse. Los detalles están en [CONTRIBUTING.md](CONTRIBUTING.md).

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
