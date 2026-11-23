# Guía de contribución

Este documento recoge las reglas de trabajo del equipo. Si algo no está aquí, se pregunta antes de improvisar.

## Modelo de ramas: EGCFlow

| Rama | Origen | Destino | Vida | Protección |
| --- | --- | --- | --- | --- |
| `main` | — | — | Permanente | Release directa desde `trunk`, tag, CI verde, sin force-push |
| `trunk` | `main` | `main` | Permanente | Integración directa de ramas revisadas, CI verde, sin force-push |
| `feature/<WI>-<slug>` | `trunk` | `trunk` | Máximo 3 días | Revisión en issue y CI verde en la rama |
| `hotfix/<slug>` | `main` | `main` y `trunk` | Máximo 24 horas | CI verde y revisión |

Reglas:

- Una rama, una tarea. No se mezclan cambios de varios issues.
- No se crean ramas por persona.
- La rama se actualiza a diario sobre `trunk` (`git rebase origin/trunk`).
- La rama se borra al fusionarse.
- `trunk` se integra en `main` cada dos semanas con merge directo y etiqueta; no se usa PR de release.

Ejemplos: `feature/72-repo-setup`, `feature/178-workflow-model`, `hotfix/doi-null`.

## Commits

Se sigue [Conventional Commits](https://www.conventionalcommits.org/):

```text
<tipo>(<ámbito>): <descripción en imperativo> (#<issue>)
```

Tipos: `feat`, `fix`, `docs`, `style`, `refactor`, `perf`, `test`, `build`, `ci`, `chore`, `revert`.

Ejemplos:

```text
feat(validation): add L1 syntactic validation (#15)
fix(zenodo): keep concept DOI on metadata update (#33)
docs(repo): add contributing guide and templates (#72)
```

Un commit, un cambio lógico. Asunto de hasta 72 caracteres. Cuerpo cuando el porqué no sea evidente.

## Integración sin pull requests (EGCFlow 0 PR)

El equipo **no usa pull requests**, tampoco para `main`. El control se hace en la issue y en el CI.

1. El autor trabaja en una rama `feature/<WI>-<slug>` creada desde `trunk`.
2. Al terminar, mueve la issue a **In review** y asigna un revisor distinto del autor.
3. El revisor examina `git diff trunk...<rama>` en un máximo de 48 horas y deja un comentario con la plantilla de revisión.
4. El autor rebasa la rama sobre `trunk`, comprueba el CI en verde y hace merge directo con historia lineal.
5. Borra la rama, cierra la issue citando el commit de integración y actualiza el tablero.

La revisión debe quedar registrada en la issue. No se acepta una plantilla dentro de un bloque de código, ni que el autor de la issue o de los commits se apruebe a sí mismo. Si el revisor pide cambios, la issue vuelve a **In progress**.

### Plantilla de revisión en la issue

```markdown
## Revisión de `feature/<WI>-<slug>`

- [x] Legibilidad y estilo (ruff, black)
- [x] Pruebas incluidas, con casos límite
- [x] CI en verde
- [x] Sin secretos
- [x] Commits con Conventional Commits y referencia a la issue
- [x] La rama se ha rebasado sobre trunk

**Resultado:** ✅ Aprobado

**Comentarios:**
...
```
## Definición de listo (DoR)

Un issue está listo cuando tiene:

- descripción y contexto;
- criterios de aceptación verificables;
- dependencias identificadas;
- estimación de tres días o menos;
- responsable y persona de apoyo;
- hito asignado.

Si no cumple esto, se queda en `Backlog`.

## Definición de terminado (DoD)

Una tarea está terminada cuando:

- el código está integrado en `trunk`;
- las pruebas pasan y la cobertura no baja;
- el CI está verde;
- la documentación o el changelog están actualizados;
- la revisión está registrada;
- el issue se cierra con evidencia (commit, captura o enlace).

## Etiquetas

| Etiqueta | Uso |
| --- | --- |
| `type:feature`, `type:bug`, `type:docs`, `type:infra`, `type:test`, `type:chore` | Tipo de trabajo |
| `area:model`, `area:ui`, `area:validation`, `area:ci`, `area:docs`, `area:testing`, `area:setup` | Área técnica |
| `priority:p0`, `priority:p1`, `priority:p2` | Urgencia |
| `scope:minimum`, `scope:extra` | Compromiso del acta o extra |
| `wi:177`, `wi:178`, `wi:192`... | Work item |
| `blocked` | Espera a que se cierre una dependencia |

## Dependencias

Antes de mover una tarjeta a `In progress`, comprueba su línea `Depends on:`.

- Si una dependencia está abierta, la tarjeta se queda en `Blocked` con la etiqueta `blocked`.
- Cuando se cierre una dependencia, revisa qué issues la esperaban y muévelos de `Blocked` a `Ready`.
- No se empieza una tarea “para ir avanzando” si su interfaz todavía no existe.

## Entorno y pruebas

```bash
cp .env.docker.example .env
docker compose -f docker/docker-compose.dev.yml up --build
```

Antes de subir una rama:

```bash
docker compose -f docker/docker-compose.dev.yml exec web \
  pytest app/features/ --ignore-glob='*selenium*'
docker compose -f docker/docker-compose.dev.yml exec web ruff check app rosemary fakenodo
docker compose -f docker/docker-compose.dev.yml exec web black --check app rosemary fakenodo
```

## Comunicación

- Issues: canal oficial y vinculante.
- Tablero: https://github.com/orgs/Action-Hub-EGC/projects/1
- Reunión semanal: lunes a las 18:00.
- Dudas que bloqueen: se avisan por el issue y por WhatsApp, en ese orden.
