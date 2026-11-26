# secure-node-ci

Integración continua para proyectos Node.js pensada como referencia de buenas prácticas.

- Todas las acciones están fijadas por SHA completo, con la versión en un comentario.
- El token solo tiene `contents: read`.
- `persist-credentials: false` evita dejar el token en el checkout.
- Cada job tiene `timeout-minutes` y las ejecuciones antiguas se cancelan con `concurrency`.
- `npm ci --ignore-scripts` no ejecuta scripts de instalación de terceros.

`fixtures/package.json` es un proyecto mínimo para probar el workflow.
