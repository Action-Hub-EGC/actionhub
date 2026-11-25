# Análisis de seguridad

Enabler E-03 (#75). Responsable: Francisco Casasola (`@Pacocc9`). Apoyo: Rafael de la Rosa (`@delarosa05`).

El workflow [`CI_security.yml`](../.github/workflows/CI_security.yml) ejecuta cuatro análisis en cada push a cualquier rama y cada lunes a las 06:00 UTC. La ejecución semanal sirve para detectar CVE publicadas después del último commit.

| Herramienta | Qué analiza | Cuándo falla |
| --- | --- | --- |
| bandit 1.9.4 | Código Python de `app`, `rosemary` y `fakenodo` (sin tests) | Hallazgo de severidad HIGH |
| pip-audit 2.10.1 | `requirements.txt` contra PyPI Advisory y OSV | Cualquier vulnerabilidad conocida no justificada |
| Trivy 0.76.2 (repositorio) | Dependencias, secretos y Dockerfiles | HIGH o CRITICAL con parche disponible |
| Trivy 0.76.2 (imagen) | Imagen de `Dockerfile.prod`: paquetes Debian y Python | HIGH o CRITICAL con parche disponible |
| CodeQL (`security-extended`) | Python y los workflows de `.github/workflows` | No bloquea; publica las alertas en *Security → Code scanning* |

bandit también genera un informe JSON con todas las severidades, que se puede descargar como artefacto `bandit-report` de cada ejecución.

El propio workflow cumple las reglas que ActionHub aplica a los workflows publicados: todas las acciones están fijadas por SHA (SEC-01), los permisos son explícitos y mínimos (SEC-02 y SEC-03), y cada job tiene `timeout-minutes` y `concurrency`. Trivy se ejecuta desde su imagen oficial fijada por digest, no con `aquasecurity/trivy-action`, porque las etiquetas de esa acción se comprometieron en 2026.

## Ejecución en local

```bash
pip install bandit==1.9.4 pip-audit==2.10.1
bandit -c pyproject.toml -r app rosemary fakenodo --severity-level high
pip-audit -r requirements.txt --no-deps --disable-pip \
  --ignore-vuln PYSEC-2026-1377 --ignore-vuln PYSEC-2026-2151 --ignore-vuln PYSEC-2026-2270
docker run --rm -v "$PWD:/src" -w /src aquasec/trivy:0.76.2 \
  fs --scanners vuln,secret,misconfig --severity HIGH,CRITICAL --ignore-unfixed .
```

## Estado inicial y correcciones (25/11/2026)

### Dependencias

La primera auditoría de `requirements.txt` encontró **174 avisos en 24 paquetes**: 8 críticos y unos 70 altos. Los críticos estaban en pillow y authlib; los altos, en mistune, pyasn1, soupsieve, python-engineio, msgpack, entre otros. Se subió cada paquete a la versión mínima que corrige todos sus avisos:

| Paquete | Antes | Después |
| --- | --- | --- |
| anyio | 4.13.0 | 4.14.2 |
| Authlib | 1.7.1 | 1.9.1 |
| black | 26.3.1 | 26.10.1 |
| bleach | 6.3.0 | 6.4.0 |
| brotli | 1.2.0 | 1.2.1 |
| certifi | 2026.4.22 | 2026.10.18 |
| cryptography | 48.0.0 | 50.0.0 |
| dnspython | 2.8.0 | 2.9.2 |
| h2 | 4.3.0 | 4.4.1 |
| hpack | 4.1.0 | 4.2.0 |
| idna | 3.13 | 3.15 |
| joserfc | 1.6.4 | 1.7.6 |
| mistune | 3.2.1 | 3.3.4 |
| msgpack | 1.1.2 | 1.2.3 |
| pillow | 12.2.0 | 13.0.0 |
| pyasn1 | 0.6.3 | 0.6.5 |
| pyOpenSSL | 26.2.0 | 26.4.0 (necesario para cryptography 50) |
| python-engineio | 4.13.1 | 4.13.2 |
| python-socketio | 5.16.1 | 5.16.2 |
| setuptools | 82.0.1 | 84.1.0 |
| soupsieve | 2.8.3 | 4.0.0 |
| urllib3 | 2.6.3 | 2.8.0 |
| Werkzeug | 3.1.8 | 3.1.9 |

La versión de black del job de lint en `CI_pipeline.yml` se actualiza también. La 26.10.1 no reformatea ningún archivo.

### Código

| Hallazgo | Archivo | Corrección |
| --- | --- | --- |
| B324 (HIGH): MD5 débil | `app/features/dataset/services.py`, `fakenodo/app.py` | Es un checksum de integridad compatible con Zenodo, no un control de seguridad. Se declara `usedforsecurity=False`. |
| B602 (HIGH): `subprocess` con `shell=True` | `rosemary/src/rosemary/commands/db_console.py` | Los argumentos se pasan como lista y sin shell. |
| Trivy DS-0029 (HIGH): `apt-get install` sin `--no-install-recommends` | `docker/images/Dockerfile.mariadb` | Se añade el flag. |
| Trivy (HIGH): libzstd1 de Debian sin el parche `deb13u1` | `docker/images/Dockerfile.prod` | La etapa final ejecuta `apt-get upgrade` para incluir los parches de seguridad que la imagen base aún no trae. |
| Trivy (HIGH): urllib3 2.7.0 y msgpack 1.1.2 incluidos en el pip de la imagen base | `docker/images/Dockerfile.prod` | Se actualiza el pip de `/usr/local`. La aplicación usa el del venv, pero el otro también estaba en la imagen. |

Pendiente: `Dockerfile.render` y `Dockerfile.webhook` usan la misma base y necesitan los mismos dos cambios. El CI solo escanea la imagen de `Dockerfile.prod`, que es la que se publica en Docker Hub.

## Excepciones justificadas

No queda ninguna vulnerabilidad crítica o alta. Las excepciones siguientes se revisaron y están configuradas en el workflow o en [`.trivyignore`](../.trivyignore):

| ID | Paquete o regla | Severidad | Justificación |
| --- | --- | --- | --- |
| PYSEC-2026-1377 (CVE-2025-47278) | Flask 3.1.0 | Baja | Solo afecta con `SECRET_KEY_FALLBACKS`, que no se usa. Flask está fijado a 3.1.0 por `splent_framework` (también en su última versión, 1.37.0). |
| PYSEC-2026-2151 (CVE-2026-27205) | Flask 3.1.0 | Baja | Falta de `Vary: Cookie` en algunos accesos a `session`. Requiere un proxy de caché que no ignore las cookies; no hay ninguno en el despliegue. Mismo bloqueo de versión. |
| PYSEC-2026-2270 (CVE-2026-28684) | python-dotenv 1.0.1 | Media (6.6) | Solo afecta a `set_key()` y `unset_key()`; el código solo usa `load_dotenv()` y `dotenv_values()`. Versión fijada por `splent_framework`. |
| B608 (MEDIUM) | `fakenodo/store.py` | Media | Falso positivo: los nombres de columna salen de una lista blanca y los valores van parametrizados. Se marca con `# nosec B608`. |

| Secreto `private-key` | `seleniumwire/ca.key` en la imagen de producción | Alta | No es un secreto del proyecto: es la CA de pruebas pública que selenium-wire incluye en su paquete de PyPI para interceptar HTTPS en los tests de Selenium. Ningún componente la marca como confiable. Llega a la imagen porque `requirements.txt` mezcla dependencias de ejecución y de test. Se excluye solo ese fichero (`--skip-files`). Pendiente: separar las dependencias de desarrollo para que selenium-wire no entre en producción. |

| CVE-2025-47273 | setuptools 70.3.0 en la imagen | Alta | Falso positivo: Trivy lo lee de `pip/_vendor/vendor.txt`, pero pip solo incluye `pkg_resources` de setuptools. La CVE está en `PackageIndex`, que no viene incluido. Está en [`.trivyignore`](../.trivyignore). |
| DS-0002 | Dockerfiles sin `USER` (los 7) | Alta | Las imágenes de desarrollo y de webhook montan el socket de Docker, así que un usuario sin privilegios no aislaría nada. Producción y Render ejecutan migraciones y escriben en volúmenes cuyo propietario es root. fakenodo, locust y mariadb son de desarrollo y pruebas. Está en [`.trivyignore`](../.trivyignore). Pendiente: usuario sin privilegios en producción. |

Los hallazgos de severidad media y baja de bandit que no bloquean se revisan en el informe: llamadas a `requests` sin `timeout` en `zenodo/services.py`, `0.0.0.0` en fakenodo dentro del contenedor y `subprocess` en los comandos de Rosemary.

## Cómo añadir una excepción

1. Comprueba que no existe una versión corregida compatible. Si existe, sube la versión.
2. Añade el ID al workflow (`--ignore-vuln`) o a `.trivyignore`, con un comentario.
3. Añade una fila en la tabla anterior con la justificación.
4. El revisor de la issue valida la justificación.
