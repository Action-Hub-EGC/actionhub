# issue-label-bot

Lee el título y el cuerpo de cada issue y le pone etiquetas.

Problemas conocidos: interpola `github.event.issue.title` y `github.event.issue.body` directamente en
`run` (inyección de comandos desde cualquier issue), usa acciones en `@main` y no declara `permissions`.
