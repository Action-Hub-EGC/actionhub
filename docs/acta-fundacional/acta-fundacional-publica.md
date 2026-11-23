---
title: "Acta fundacional"
project: "ActionHub"
subtitle: "Acuerdos de constitución del equipo"
code: "AH-ACT-001"
version: "1.0"
date: "7 de noviembre de 2026"
status: "Versión pública sin firmas"
doc_label: "EGC 2026/2027"
---

> **Versión pública sin firmas.** El original firmado se entregó al tutor/a. Esta copia mantiene el contenido y los roles, pero omite firmas, UVUS y correos institucionales.

> **Nota de vigencia (23/11/2026).** La política de PR descrita en este acta se sustituye por el ACTA-2026-09: EGCFlow sin PRs, revisión en la issue y CI en todas las ramas.

# Acta fundacional — ActionHub

**Versión pública sin firmas · 7 de noviembre de 2026**

# 1. Identificación del equipo

El equipo se constituye como **Grupo 1** de la asignatura Evolución y Gestión de la Configuración (EGC) durante el curso 2026/2027. La siguiente tabla recoge los datos básicos del proyecto y del grupo.

| Campo | Valor |
| --- | --- |
| Nombre del grupo | Equipo ActionHub |
| Nombre técnico | action-hub |
| Grupo | Grupo 1 |
| Proyecto | ActionHub, registro abierto de workflows de GitHub Actions |
| Asignatura | Evolución y Gestión de la Configuración (EGC) |
| Curso académico | 2026/2027 |
| Centro | Escuela Técnica Superior de Ingeniería Informática |
| Universidad | Universidad de Sevilla |
| Tutor | Equipo docente de EGC |
| Repositorio | github.com/Action-Hub-EGC/action-hub |
| Canal oficial | GitHub Issues y GitHub Discussions |
| Fecha de emisión | 7 de noviembre de 2026 |
| Entrada en vigor | 9 de noviembre de 2026 |

## 1.1 Integrantes

| # | Nombre y apellidos | Usuario de GitHub | Rol |
| --- | --- | --- | --- |
| 1 | Marcos Ángel Ayala Blanco | GBK4935 | Jefe de Proyecto |
| 2 | Rafael de la Rosa Regaña | delarosa05 | DevOps |
| 3 | Jaime García-Castillejo Carmona | JaimeGarcia2005 | Desarrollador |
| 4 | José Fernando Gutiérrez Montero | Jfgm299 | Desarrollador |
| 5 | Francisco Casasola Calzadilla | Pacocc9 | DevOps |
| 6 | Alejandro Ramos Rivera | Alexr-z | Desarrollador |

## 1.2 Control del documento

| Campo | Valor |
| --- | --- |
| Versión | 1.0 |
| Estado | Versión pública sin firmas |
| Autoría | Equipo ActionHub (Grupo 1) |
| Revisión | Tutor/a del equipo |
| Licencia | CC BY 4.0 |
| Documento completo | AH-ACT-001 |

# 2. Tipo de hub

La idea de ActionHub salió de una pregunta bastante concreta: si casi todos los proyectos usan GitHub Actions, ¿por qué no hay un sitio donde consultar qué automatizaciones existen y si son seguras? GitHub Marketplace distribuye acciones sueltas, pero no evalúa workflows completos ni dice nada sobre su seguridad.

En la práctica, la mayoría de los equipos copian un workflow de otro repositorio, cambian un par de líneas y lo dejan funcionando. Nadie comprueba si las acciones están fijadas a una versión concreta, si los permisos son excesivos o si el workflow sigue manteniéndose. ActionHub quiere cubrir ese hueco: un catálogo abierto, con validación automática y una nota de seguridad visible antes de descargar.

## 2.1 Definición

> ActionHub es un registro abierto de workflows de GitHub Actions. Cada automatización se publica como un paquete versionado, se valida automáticamente, se audita en seguridad con una calificación de A a F y se puede citar con DOI a través de Zenodo o de su equivalente de pruebas, fakenodo.

El hub es un fork de UVLHub. De él hereda la publicación, la autoría, las licencias, la búsqueda y el depósito de identificadores. Lo que cambia es el tipo de dato: en lugar de modelos de características en formato UVL, ActionHub trabaja con workflows. Para que esa convivencia sea posible, el modelo se reorganiza en una base común, BaseDataset, y un tipo específico, WorkflowDataset. La validación de UVL que hacía flamapy se sustituye por un pipeline propio. La propuesta de nuevo tipo de dataset, que se corresponde con el WI-newdataset, queda sujeta a la aceptación formal del tutor en el primer seguimiento.

El equipo se marca tres objetivos con este proyecto:

- Publicar workflows útiles y fáciles de encontrar por lo que hacen.
- Mostrar la calidad y la seguridad antes de descargar, no después de romper una integración.
- Permitir que cada versión se cite y se reproduzca, como se hace con un artículo o un dataset.

## 2.2 El problema y la propuesta

El problema no es teórico. En marzo de 2025 se comprometió la acción tj-actions/changed-files, muy utilizada para detectar cambios en pull requests. Un atacante modificó una etiqueta y consiguió que miles de repositorios ejecutaran código ajeno sin haber cambiado nada. No fue un fallo de GitHub, sino de la forma en que se consume el ecosistema: se referencia una acción por etiqueta, se le dan permisos amplios y nadie revisa qué hay detrás.

ActionHub responde con cuatro piezas dentro de su alcance mínimo:

- **Validación obligatoria sintáctica (L1) y de esquema (L2)** antes de publicar. Si el workflow no es válido, no aparece.
- **Calificación de seguridad de A a F (L4)** mediante reglas propias con penalizaciones objetivas.
- **Extracción de metadatos básicos del workflow**: disparadores (on), trabajos (jobs), runners y acciones utilizadas (uses).
- **Versionado mayor y citación**: DOI por versión con fakenodo y badge embebible con la calificación.

## 2.3 Por qué ActionHub y no un hub de YAML

La primera propuesta del equipo fue un hub de ficheros YAML. La descartamos nosotros mismos al ver que YAML es una sintaxis, no un dominio. Un hub de «cualquier YAML» no tiene un criterio claro de qué es válido, no produce metadatos comparables y no resuelve ningún problema concreto. Un workflow, en cambio, tiene un esquema público, una semántica de ejecución y un ciclo de vida. Ahí sí se puede validar, medir y comparar.

Se evaluaron cinco alternativas con seis criterios ponderados: especificidad del dominio, validación determinista, riqueza de metadatos, utilidad real, viabilidad en el plazo y relación con la asignatura.

| Alternativa | Puntuación | Decisión |
| --- | --- | --- |
| ActionHub | 4,6 | Seleccionada, pendiente de aceptación por el tutor |
| ComposeHub | 4,1 | Plan de contingencia |
| APIHub | 3,9 | Descartada |
| IaCHub | 3,8 | Descartada |
| MLReproHub | 3,4 | Descartada |
| YAMLHub genérico | 1,8 | Descartada |

ActionHub gana porque el workflow es el dominio y no el formato, la validación mínima (L1, L2 y L4) es determinista y se puede ejecutar en Python sin depender de escáneres externos ni de la API de GitHub, los metadatos son ricos y el proyecto aplica las prácticas de EGC a un objeto propio de EGC: la automatización y el despliegue continuo.

## 2.4 Unidad de publicación y ciclo de vida

Un dataset de ActionHub es un directorio con esta estructura:

| Fichero o directorio | Contenido y función en el paquete |
| --- | --- |
| actionhub.yaml | Manifiesto de metadatos, fuente de verdad, validado con un JSON Schema propio. |
| workflow.yml | El workflow de GitHub Actions que se valida, audita y publica. |
| README.md | Descripción, instrucciones de uso, entradas y salidas. |
| LICENSE | Licencia SPDX del paquete. |
| CHANGELOG.md y fixtures/ | Histórico legible y repositorio mínimo de ejemplo, ambos opcionales. |

El ciclo de vida del dataset contempla tres estados: draft (borrador en edición), validated (superadas las capas bloqueantes L1 y L2 y calculada su nota L4) y published (publicado con DOI asignado en fakenodo). El versionado mayor genera una nueva versión vinculada al dataset sin añadir un estado versioned separado.

## 2.5 Validación y calificación

La validación se organiza en cuatro capas. Las dos primeras son bloqueantes y forman parte del alcance mínimo. La tercera y la cuarta son extras: se harán si el calendario lo permite y no cuentan como incumplimiento si no se llegan a completar.

| Capa | Comprobación | Herramienta | ¿Bloquea? | Alcance |
| --- | --- | --- | --- | --- |
| L1. Sintáctica | YAML bien formado, sin claves duplicadas | ruamel.yaml | Sí | Mínimo |
| L2. Esquema | Estructura conforme al esquema oficial | jsonschema y SchemaStore | Sí | Mínimo |
| L3. Estática | Expresiones, dependencias entre jobs y runners | actionlint en contenedor | No | Extra |
| L4. Dominio y seguridad | Reglas propias de seguridad de ActionHub | Motor de reglas en Python | No | Mínimo (SEC-01 a SEC-04) |

La puntuación parte de 100 y aplica las penalizaciones de las reglas incumplidas, sin bajar nunca de 0: max(0, 100 − penalizaciones). En el alcance mínimo se contemplan cuatro reglas principales:

- **SEC-01**: fijar toda acción externa por SHA completo, con −15 puntos por cada acción sin fijar y un máximo de −45.
- **SEC-02**: declarar permissions, con −10 puntos una sola vez por workflow.
- **SEC-03**: no usar write-all, con −10 puntos una sola vez por workflow.
- **SEC-04**: no combinar pull_request_target con checkout del head, con −25 puntos por cada aparición.

Como extras quedan no interpolar entrada no confiable en run (−20), no escribir secretos en texto plano (−20), definir timeout-minutes (−3 por job, con un límite) y usar concurrency en despliegues (−5 una vez).

| Puntuación | 90–100 | 80–89 | 70–79 | 60–69 | 50–59 | 0–49 |
| --- | --- | --- | --- | --- |
| Calificación | A | B | C | D | E | F |

Un workflow con errores en L1 o L2 no se publica. La capa L4 no es bloqueante: una calificación inferior a C se publica mostrando una advertencia de seguridad.

## 2.6 Alcance y work items

El proyecto se desarrolla en cinco semanas. Para que el compromiso sea realista, el equipo separa lo que se compromete a entregar de lo que hará si sobra tiempo. Esta distinción es importante: los extras no cuentan como incumplimiento si no se alcanzan.

| Mínimo comprometido | Extras, si da tiempo | Fuera del alcance |
| --- | --- | --- |
| Subida, publicación y descarga de workflows (#178). | actionlint (L3) en contenedor. | Ejecución de workflows o alojamiento de runners. |
| Validación sintáctica (L1) y de esquema (L2). | Resto del catálogo de reglas L4. | Réplica completa de la API de Zenodo. |
| Metadatos básicos: disparadores, jobs y acciones usadas. | Métricas avanzadas que requieren consultar la API de GitHub: frescura, SHA resuelto, acción archivada o coste estimado. | Ediciones menores y diferencias entre versiones. |
| Reglas de seguridad SEC-01 a SEC-04 y calificación A–F. | Pruebas E2E con Selenium y carga con Locust, informativas. | API pública con claves y hash revocables (#207) y app móvil. |
| fakenodo (#177) y los seis work items asignados. | mypy, CodeQL, Trivy, entorno de staging y 30 paquetes curados en 8 categorías. | Integración con otros proveedores de CI. |
| CI bloqueante: estilo, tests unitarios y de integración, cobertura y build de Docker. |  |  |
| Entorno reproducible con docker compose up. |  |  |

# 3. Roles y responsabilidades

El equipo tiene seis personas y tres perfiles: un jefe de proyecto, dos DevOps y tres desarrolladores. Todos participamos en el desarrollo y en las revisiones. El rol indica la responsabilidad principal sobre un área, no una frontera: las tareas se asignan por work item y cualquiera puede aportar en cualquier parte del proyecto.

## 3.1 Asignación y reparto de work items

| Persona | Rol | Responsabilidad principal |
| --- | --- | --- |
| Marcos Ángel Ayala Blanco | Jefe de Proyecto | Planificación, priorización, riesgos, relación con el tutor y releases |
| Rafael de la Rosa Regaña | DevOps | CI/CD, Docker, despliegue, entornos y observabilidad |
| Jaime García-Castillejo Carmona | Desarrollador | Validación L1/L2, reglas de dominio L4 y estrategia de pruebas |
| José Fernando Gutiérrez Montero | Desarrollador | Modelo de datos (BaseDataset y WorkflowDataset), versionado y lógica de negocio |
| Francisco Casasola Calzadilla | DevOps | Servicio fakenodo, entornos aislados y seguridad de dependencias |
| Alejandro Ramos Rivera | Desarrollador | Interfaz, exploración con facetas, documentación y demo |

Cada work item tiene un responsable principal y una persona de apoyo. La idea es que nadie se quede solo con una parte crítica y que el conocimiento circule.

| Tipo | Issue | Capacidad | Responsable | Apoyo |
| --- | --- | --- | --- | --- |
| Común | #178 | BaseDataset, WorkflowDataset, validación propia y migración | J. F. Gutiérrez | J. García |
| Común | #177 | fakenodo: simulación de la API de Zenodo | F. Casasola | R. de la Rosa |
| Alta (H1) | #196 | Versionado mayor de datasets | J. F. Gutiérrez | F. Casasola |
| Alta (H2) | #197 | Historial y navegación entre versiones | J. García-Castillejo | J. F. Gutiérrez |
| Media (M1) | #194 | Búsqueda avanzada con facetas | A. Ramos | J. García-Castillejo |
| Media (M2) | #213 | Badge embebible con la calificación | R. de la Rosa | A. Ramos |
| Baja (L1) | #192 | Panel de métricas de uso | M. Á. Ayala | R. de la Rosa |
| Baja (L2) | #214 | Contador de descargas | F. Casasola | M. Á. Ayala |

## 3.2 Matriz RACI

A = aprueba, R = ejecuta, C = se le consulta, I = se le informa.

| Actividad | M. Ayala | R. de la Rosa | J. García | J. Gutiérrez | F. Casasola | A. Ramos |
| --- | --- | --- | --- | --- |
| Acta y diario | A | I | I | I | I | R |
| Dominio y reglas | C | I | R | A | C | I |
| Priorización de WIs | A | C | C | R | C | I |
| Arquitectura | C | C | A | R | C | I |
| Pipeline de validación | I | C | A | C | R | I |
| CI/CD y entornos | I | A | C | C | R | I |
| Estrategia de pruebas | I | C | A | C | C | R |
| Seguridad y dependencias | A | C | C | C | R | I |
| Releases | A | R | C | C | C | I |
| Documentación y demo | A | I | C | I | I | R |

## 3.3 Toma de decisiones

Las decisiones se buscan por consenso. Si no se alcanza en dos rondas, se vota por mayoría simple y el jefe de proyecto ejerce el voto de calidad. Las decisiones que afectan al alcance, al dominio o a la seguridad requieren el visto bueno del tutor/a, y quedan registradas en las actas y en el diario del equipo.

# 4. Acuerdos de comunicación

Con seis personas y cinco semanas, la comunicación es parte del trabajo, no un añadido. El equipo acuerda un canal para cada cosa y una regla sencilla: lo que no está escrito en el repositorio no existe.

## 4.1 Canales

| Canal | Uso | Carácter |
| --- | --- | --- |
| GitHub Issues | Trabajo, criterios de aceptación y discusión técnica | Oficial y vinculante |
| GitHub Discussions | Propuestas, actas y decisiones abiertas | Oficial y vinculante |
| GitHub Projects | Tablero y estado del trabajo | Oficial |
| WhatsApp | Avisos urgentes y coordinación inmediata | No vinculante |
| Correo institucional | Comunicación con el tutor | Oficial |

Ninguna decisión existe hasta que está escrita en el repositorio. Lo acordado por voz o por mensajería se traslada a un issue o al diario en menos de 24 horas.

## 4.2 Reuniones

Para no consumir las ocho horas semanales comprometidas en reuniones excesivas, se fija una única reunión general semanal de 60 minutos, complementada con seguimiento asíncrono en issues y en el tablero.

| Reunión o seguimiento | Cuándo | Duración | Salida |
| --- | --- | --- | --- |
| Reunión semanal de equipo | Lunes, 18:00 | 60 min | Objetivos, asignaciones, revisión y acta |
| Seguimiento asíncrono | Miércoles, en Issues y tablero | Asíncrono | Actualización de estado y bloqueos |
| Seguimiento con el tutor | 9, 23 y 30 de noviembre | 30 min | Revisión de hitos, acuerdos y tareas |

La agenda de la reunión semanal se publica 24 horas antes y el acta 24 horas después.

## 4.3 Tiempos de respuesta

| Situación | Compromiso, contando días lectivos |
| --- | --- |
| Mención directa en un issue o bloqueo declarado | 24 horas, con aviso inmediato por WhatsApp si es un bloqueo |
| Solicitud de revisión de código | 48 horas |
| Entrega de tarea | Antes de la fecha acordada, con aviso previo si existe riesgo de retraso |

# 5. Política de ramas

El equipo adopta EGCFlow, el modelo de la asignatura: una rama main que actúa como release, una rama trunk de integración y ramas cortas de tarea que se fusionan con frecuencia. No se usa GitFlow y no se crean ramas por persona.

## 5.1 Modelo EGCFlow

| Rama | Origen | Destino | Vida | Protección |
| --- | --- | --- | --- | --- |
| main | — | — | Permanente | PR, dos aprobaciones, CI verde, sin push directo |
| trunk | main | main | Permanente | CI verde, sin force-push |
| feature/<WI>-<slug> | trunk | trunk | Máximo 3 días | CI verde en la rama (por ejemplo, feature/178-schema) |
| hotfix/<slug> | main | main y trunk | Máximo 24 horas | CI verde y revisión |

No se usan ramas por persona ni GitFlow. Las ramas se actualizan a diario sobre trunk y se eliminan tras la fusión. Las etiquetas de versión sobre main se alinean con los hitos y seguimientos: v0.1 el 16 de noviembre, v0.2 el 23 de noviembre, coincidiendo con el segundo seguimiento, y v0.3 el 30 de noviembre, coincidiendo con el tercero.

## 5.2 Commits y revisión

Se sigue Conventional Commits: tipo(ámbito): descripción (#issue). Un ejemplo real del proyecto sería feat(validation): add L1 and L2 checks (#178). Los tipos admitidos son feat, fix, docs, style, refactor, perf, test, build, ci, chore y revert.

EGCFlow no exige PR para integrar cada cambio menor en trunk. Se exige cuando el cambio incluye una migración, modifica CI/CD, toca autenticación o permisos, supera 400 líneas o afecta a otro módulo. El resto se revisa por pares antes de fusionar, dejando constancia en el issue. En el pipeline de CI solo son bloqueantes el estilo, los tests unitarios y de integración, la cobertura y el build de Docker.

> **Nota de vigencia (23/11/2026):** esta política de PR se sustituye por el ACTA-2026-09. Desde esa fecha, EGCFlow se aplica sin PRs: revisión en la issue, integración directa en `trunk` y release directa a `main` con etiqueta.

## 5.3 Listo y terminado

- **Listo (DoR):** descripción clara, criterios de aceptación verificables, impacto en el dominio, dependencias y plan de pruebas. Los WIs grandes se dividen en sub-issues con una estimación de tres días o menos cada uno.
- **Terminado (DoD):** código integrado, pruebas en verde, cobertura sin bajar, documentación actualizada, CI verde, revisión registrada, issue cerrado con evidencia y entrada en el changelog.

# 6. Régimen interno y sanciones

## 6.1 Compromisos

- Ocho horas semanales mínimas de trabajo efectivo, con una franja de coincidencia declarada.
- Asistencia al 90 % de las reuniones semanales, con aviso previo cuando no sea posible.
- Respuesta a menciones y bloqueos en 24 horas en días lectivos.
- Una revisión de código por semana como mínimo y tablero actualizado antes de cada planificación.

## 6.2 Escalado de incumplimientos

| Nivel | Situación | Medida | Plazo |
| --- | --- | --- | --- |
| L1. Aviso | Olvido puntual o retraso menor de 24 horas | Aviso privado y anotación en el diario | 48 horas |
| L2. Plan de recuperación | Dos avisos en catorce días, falta sin aviso o 72 horas sin responder | Plan escrito con hitos; se informa al tutor y, si persiste, al coordinador | 7 días |
| L3. Mediación | Dos planes incumplidos o una semana sin actividad | Mediación del tutor; si no se resuelve, del coordinador de la asignatura | Según tutor |
| L4. Separación | Abandono superior a catorce días o falta académica grave | Separación con intervención del coordinador, según la normativa de la US | Inmediato |

Las medidas son acumulativas y se registran. La persona afectada puede aportar su versión antes de cualquier medida distinta del aviso.

## 6.3 Umbrales objetivos

- 72 horas en días lectivos sin respuesta a una mención directa sin causa justificada.
- Dos reuniones consecutivas sin asistencia ni aviso.
- Una semana sin commits, revisiones ni comentarios en una tarea asignada.
- Un hito entregado con más de cinco días de retraso por causa imputable a una persona.

Las ausencias por enfermedad, causas familiares graves o exámenes oficiales no computan como incumplimiento.

## 6.4 Conflictos

El escalado general sigue cuatro pasos: primero, conversación directa entre las partes; segundo, mediación del jefe de proyecto escuchando ambas versiones; tercero, mediación del tutor/a, si no hay acuerdo en 48 horas; y cuarto, en caso de conflicto grave, se acude cuanto antes al coordinador de la asignatura con constancia previa en el acta y en el diario, para reconducir la situación sin perjudicar a ninguna de las partes. Ante los conflictos frecuentes señalados en la asignatura se actuará así:

| Conflicto frecuente | Acción a realizar |
| --- | --- |
| Algún miembro no trabaja, no acude a las reuniones, no contesta a los mensajes o no presta interés en el equipo. | Aplicar de inmediato los límites objetivos de 6.2 y 6.3 y no dejar pasar el tiempo. Hacer constar en el acta y en el diario la situación y comunicarlo al tutor y al coordinador para, en su caso, dar de baja al miembro o intentar mediar en el conflicto. |
| Se tienen puntos de vista distintos sobre determinados temas del trabajo. | El equipo superará internamente la situación mediante debate objetivo y el sistema de decisión de 3.3. Solo en caso extremo de bloqueo se acudirá al coordinador para que medie. |
| Hay niveles distintos de interés o habilidades en el equipo y eso hace que haya partes que se hagan mejor y otras peor. | El equipo solucionará esta situación mediante el trabajo en pareja (responsable y apoyo): las personas con más interés o soltura acompañarán, motivarán y enseñarán a quienes tengan menos, pues enseñando también se aprende y cooperar con el resto es síntoma de buen liderazgo. |

## 6.5 Integridad académica y uso de IA

Dado que el repositorio del proyecto es público, se permite el uso de asistentes de IA como apoyo al código y a la documentación, con cuatro condiciones: quien firma un cambio debe poder explicarlo individualmente en las defensas; los cambios sustanciales asistidos se declaran en el PR o en el issue; ningún código generado se integra sin pruebas y revisión por pares; y no se comparten datos personales de compañeros ni credenciales o tokens privados en herramientas externas. El incumplimiento grave de integridad académica se sanciona conforme al nivel L4.

# 7. Aprobación

El acta funcional de constitución entra en vigor el 9 de noviembre de 2026 y puede modificarse por consenso del equipo, con registro de la versión y aprobación del tutor/a cuando afecte al alcance.

El documento original firmado por los seis integrantes se entregó al tutor/a. Esta versión pública omite las firmas manuscritas, los UVUS y los correos institucionales para no exponer datos personales.

En Sevilla, a 7 de noviembre de 2026.