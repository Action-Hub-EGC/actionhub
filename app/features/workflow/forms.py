from flask_wtf import FlaskForm
from flask_wtf.file import FileAllowed, FileField, FileRequired
from wtforms import StringField, SubmitField


class WorkflowPackageForm(FlaskForm):
    package = FileField(
        "Paquete (.zip)",
        validators=[
            FileRequired(),
            FileAllowed(["zip"], "Solo se aceptan paquetes .zip."),
        ],
    )
    submit = SubmitField("Validar y guardar borrador")


class WorkflowDatasetForm(FlaskForm):
    """Legacy metadata form kept for compatibility with older imports."""

    title = StringField("Title")
    submit = SubmitField("Continue")
