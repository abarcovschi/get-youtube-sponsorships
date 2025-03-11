from flask_wtf import FlaskForm
from wtforms import StringField, DecimalField, SubmitField, URLField
from wtforms.validators import DataRequired

class MultipleVideosForm(FlaskForm):
    handle = StringField('Channel Handle', validators=[DataRequired()])
    num_vids = DecimalField('Number of most recent videos', validators=[DataRequired()])
    submit = SubmitField('Submit')

class SingleVideoForm(FlaskForm):
    url = URLField('Video URL', validators=[DataRequired()])
    submit = SubmitField('Submit')