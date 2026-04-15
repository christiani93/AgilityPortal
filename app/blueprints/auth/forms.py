from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField, BooleanField
from wtforms.validators import DataRequired, Email, Length, EqualTo


class LoginForm(FlaskForm):
    email = StringField("E-Mail", validators=[DataRequired(), Email()])
    password = PasswordField("Passwort", validators=[DataRequired()])
    remember = BooleanField("Angemeldet bleiben")
    submit = SubmitField("Einloggen")


class RegisterForm(FlaskForm):
    first_name = StringField("Vorname", validators=[DataRequired(), Length(max=100)])
    last_name = StringField("Nachname", validators=[DataRequired(), Length(max=100)])
    email = StringField("E-Mail", validators=[DataRequired(), Email(), Length(max=255)])
    password = PasswordField(
        "Passwort",
        validators=[DataRequired(), Length(min=8, message="Mindestens 8 Zeichen.")],
    )
    password2 = PasswordField(
        "Passwort bestätigen",
        validators=[DataRequired(), EqualTo("password", message="Passwörter stimmen nicht überein.")],
    )
    submit = SubmitField("Konto erstellen")
