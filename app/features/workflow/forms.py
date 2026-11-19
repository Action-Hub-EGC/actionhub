from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField, TextAreaField
from wtforms.validators import URL, DataRequired, Optional


class WorkflowDatasetForm(FlaskForm):
    """Minimal metadata form. The package upload arrives in #14."""

    title = StringField("Title", validators=[DataRequired()])
    description = TextAreaField("Description", validators=[DataRequired()])
    repository_url = StringField("Repository URL", validators=[Optional(), URL()])
    tags = StringField("Tags (separated by commas)")
    submit = SubmitField("Continue")
