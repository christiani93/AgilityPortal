from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField, SelectField
from wtforms.validators import DataRequired, Email, Length, EqualTo, Optional


class AddUserForm(FlaskForm):
    first_name = StringField("Vorname", validators=[DataRequired(), Length(max=100)])
    last_name = StringField("Nachname", validators=[DataRequired(), Length(max=100)])
    email = StringField("E-Mail", validators=[DataRequired(), Email(), Length(max=255)])
    role = SelectField(
        "Rolle",
        choices=[("handler", "Mitglied / Hundeführer")],
        default="handler",
    )
    password = PasswordField(
        "Passwort",
        validators=[DataRequired(), Length(min=8, message="Mindestens 8 Zeichen.")],
    )
    password2 = PasswordField(
        "Passwort bestätigen",
        validators=[DataRequired(), EqualTo("password", message="Passwörter stimmen nicht überein.")],
    )
    submit = SubmitField("Benutzer erstellen")


class ChangePasswordForm(FlaskForm):
    password = PasswordField(
        "Neues Passwort",
        validators=[DataRequired(), Length(min=8, message="Mindestens 8 Zeichen.")],
    )
    password2 = PasswordField(
        "Passwort bestätigen",
        validators=[DataRequired(), EqualTo("password", message="Passwörter stimmen nicht überein.")],
    )
    submit = SubmitField("Passwort ändern")
