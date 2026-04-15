from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField, SelectField, DateField, IntegerField
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


# ---------------------------------------------------------------------------
# Turnier
# ---------------------------------------------------------------------------

class EventForm(FlaskForm):
    ais_turniernummer = IntegerField("Turnier-ID (AIS)", validators=[Optional()])
    name = StringField("Turniername", validators=[DataRequired(), Length(max=200)])
    location = StringField("Ort", validators=[Optional(), Length(max=200)])
    starts_at = DateField("Von (Datum)", validators=[DataRequired()])
    ends_at = DateField("Bis (Datum)", validators=[Optional()])
    # Nur für Superadmin befüllt — choices werden in der Route gesetzt
    club_id = SelectField("Verein", coerce=int, validators=[Optional()])
    submit = SubmitField("Speichern")


class EventRunForm(FlaskForm):
    run_type = SelectField(
        "Typ",
        choices=[
            ("agility", "Agility"),
            ("jumping", "Jumping"),
            ("open", "Open"),
        ],
    )
    category = SelectField(
        "Kategorie",
        choices=[
            ("S", "Small (S)"),
            ("M", "Medium (M)"),
            ("I", "Intermediate (I)"),
            ("L", "Large (L)"),
        ],
    )
    class_level = SelectField(
        "Klasse",
        choices=[("1", "Klasse 1"), ("2", "Klasse 2"), ("3", "Klasse 3")],
        coerce=int,
    )
    submit = SubmitField("Lauf hinzufügen")
