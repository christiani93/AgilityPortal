from flask_babel import lazy_gettext as _
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField, BooleanField
from wtforms.validators import DataRequired, Email, Length, EqualTo


class LoginForm(FlaskForm):
    email = StringField(_("E-Mail"), validators=[DataRequired(), Email()])
    password = PasswordField(_("Passwort"), validators=[DataRequired()])
    remember = BooleanField(_("Angemeldet bleiben"))
    submit = SubmitField(_("Einloggen"))


class RegisterForm(FlaskForm):
    first_name = StringField(_("Vorname"), validators=[DataRequired(), Length(max=100)])
    last_name = StringField(_("Nachname"), validators=[DataRequired(), Length(max=100)])
    email = StringField(_("E-Mail"), validators=[DataRequired(), Email(), Length(max=255)])
    password = PasswordField(
        _("Passwort"),
        validators=[DataRequired(), Length(min=8, message=_("Mindestens 8 Zeichen."))],
    )
    password2 = PasswordField(
        _("Passwort bestätigen"),
        validators=[DataRequired(), EqualTo("password", message=_("Passwörter stimmen nicht überein."))],
    )
    submit = SubmitField(_("Konto erstellen"))
