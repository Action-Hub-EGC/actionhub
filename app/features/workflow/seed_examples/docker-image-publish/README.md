# docker-image-publish

Publica `ghcr.io/<repo>:<tag>` cada vez que se empuja una etiqueta `v*`.

Los permisos están acotados (`contents: read`, `packages: write`), pero las acciones de terceros
van fijadas por etiqueta mayor y el job no tiene `timeout-minutes`.
