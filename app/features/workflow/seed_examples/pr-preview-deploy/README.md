# pr-preview-deploy

**No lo uses.** Es el ejemplo de nota F del catálogo y reúne los fallos más graves:

- `pull_request_target` con checkout del código de la PR (`head.sha`) y ejecución de ese código con secretos.
- `permissions: write-all`.
- Acciones sin fijar (`@master`), una de ellas de un autor desconocido.
- Secretos impresos con `echo` en el log.
- `curl | sudo bash` de un script remoto.
- Sin `timeout-minutes`.
