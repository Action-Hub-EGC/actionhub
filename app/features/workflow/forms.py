from flask_wtf import FlaskForm
from flask_wtf.file import FileAllowed, FileField, FileRequired
from wtforms import SubmitField


class WorkflowPackageForm(FlaskForm):
    package = FileField(
        "Paquete (.zip)",
        validators=[
            FileRequired(),
            FileAllowed(["zip"], "Solo se aceptan paquetes .zip."),
        ],
    )
    submit = SubmitField("Validar y guardar borrador")
