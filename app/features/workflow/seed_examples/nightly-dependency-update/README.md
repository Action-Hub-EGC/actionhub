# nightly-dependency-update

Cada noche actualiza `package.json` y abre una pull request.

No declara `permissions`, así que hereda los permisos por defecto del repositorio, usa un token
personal (`BOT_TOKEN`) con más alcance del necesario, ejecuta `npx` sin versión fijada y no tiene
límite de tiempo.
