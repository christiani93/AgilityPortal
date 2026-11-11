from flask_babel import lazy_gettext as _
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField, SelectField, DateField, IntegerField, TextAreaField, BooleanField, DecimalField
from wtforms.validators import DataRequired, Email, Length, EqualTo, Optional, NumberRange


class AddUserForm(FlaskForm):
    first_name = StringField(_("Vorname"), validators=[DataRequired(), Length(max=100)])
    last_name = StringField(_("Nachname"), validators=[DataRequired(), Length(max=100)])
    email = StringField(_("E-Mail"), validators=[DataRequired(), Email(), Length(max=255)])
    role = SelectField(
        _("Rolle"),
        choices=[("handler", _("Mitglied / Hundeführer"))],
        default="handler",
    )
    password = PasswordField(
        _("Passwort"),
        validators=[DataRequired(), Length(min=8, message=_("Mindestens 8 Zeichen."))],
    )
    password2 = PasswordField(
        _("Passwort bestätigen"),
        validators=[DataRequired(), EqualTo("password", message=_("Passwörter stimmen nicht überein."))],
    )
    submit = SubmitField(_("Benutzer erstellen"))


class ChangePasswordForm(FlaskForm):
    password = PasswordField(
        _("Neues Passwort"),
        validators=[DataRequired(), Length(min=8, message=_("Mindestens 8 Zeichen."))],
    )
    password2 = PasswordField(
        _("Passwort bestätigen"),
        validators=[DataRequired(), EqualTo("password", message=_("Passwörter stimmen nicht überein."))],
    )
    submit = SubmitField(_("Passwort ändern"))


# ---------------------------------------------------------------------------
# Turnier
# ---------------------------------------------------------------------------

class EventForm(FlaskForm):
    ais_turniernummer       = IntegerField(_("Turnier-ID (AIS)"), validators=[Optional()])
    ais_turniernummer_extra = StringField(_("Weitere AIS-Nummern (Mehrtage-Event)"), validators=[Optional(), Length(max=255)])
    name = StringField(_("Turniername"), validators=[DataRequired(), Length(max=200)])
    location = StringField(_("Ort / Adresse"), validators=[Optional(), Length(max=200)])
    starts_at = DateField(_("Von (Datum)"), validators=[DataRequired()])
    ends_at = DateField(_("Bis (Datum)"), validators=[Optional()])
    registration_open_at = DateField(_("Meldebeginn"), validators=[Optional()])
    registration_close_at = DateField(_("Nennschluss"), validators=[Optional()])
    registration_external = BooleanField(_("Anmeldung läuft über externes Portal"))
    registration_url = StringField(_("Link zum externen Anmeldeportal"), validators=[Optional(), Length(max=500)])
    pruefungsleiter = StringField(_("Prüfungsleiter"), validators=[Optional(), Length(max=255)])
    max_participants = IntegerField(_("Max. Starter"), validators=[Optional(), NumberRange(min=1)])
    entry_fee = DecimalField(_("Startgeld (CHF)"), validators=[Optional(), NumberRange(min=0)], places=2)
    allows_bitches_in_season = BooleanField(_("Läufige Hündinnen erlaubt"))
    bitches_in_season_start_last = BooleanField(_("Läufige Hündinnen starten am Schluss der Kategorie"))
    notes_public = TextAreaField(_("Bemerkungen (öffentlich)"), validators=[Optional()])
    is_test = BooleanField(_("Testveranstaltung (nicht öffentlich sichtbar)"))
    special_ruleset = SelectField(
        _("Spezialturnier / Zusatzreglement"),
        choices=[
            ("", _("— Kein Spezialturnier —")),
            ("halloween_cup", "Halloween Cup"),
            ("advents_cup", "Advents Cup"),
            ("edelweiss_challenge", "Edelweiss Challenge"),
        ],
        validators=[Optional()],
    )
    # Nur für Superadmin befüllt — choices werden in der Route gesetzt
    club_id = SelectField(_("Verein"), coerce=int, validators=[Optional()])
    submit = SubmitField(_("Speichern"))


class EventRunForm(FlaskForm):
    run_type = SelectField(
        _("Typ"),
        choices=[
            ("agility", _("Agility")),
            ("jumping", _("Jumping")),
            ("open", _("Open")),
            ("tunnel", _("Tunnellauf")),
        ],
    )
    category = SelectField(
        _("Kategorie"),
        choices=[
            ("L", _("Large (L)")),
            ("I", _("Intermediate (I)")),
            ("M", _("Medium (M)")),
            ("S", _("Small (S)")),
        ],
    )
    class_level = SelectField(
        _("Klasse"),
        choices=[("1", _("Klasse 1")), ("2", _("Klasse 2")), ("3", _("Klasse 3"))],
        coerce=int,
    )
    submit = SubmitField(_("Lauf hinzufügen"))


# ---------------------------------------------------------------------------
# Anfragen an Superadmin
# ---------------------------------------------------------------------------

class JudgeRequestForm(FlaskForm):
    judge_ais_id = IntegerField(_("AIS-Nr. (falls bekannt)"), validators=[Optional()])
    judge_first_name = StringField(_("Vorname"), validators=[DataRequired(), Length(max=100)])
    judge_last_name = StringField(_("Nachname"), validators=[DataRequired(), Length(max=100)])
    note = TextAreaField(_("Bemerkung"), validators=[Optional()])
    submit = SubmitField(_("Anfrage senden"))


class ClubRequestForm(FlaskForm):
    club_vereinsnummer = StringField(_("SKG-Vereinsnummer"), validators=[DataRequired(), Length(max=20)])
    club_name = StringField(_("Vereinsname"), validators=[DataRequired(), Length(max=255)])
    note = TextAreaField(_("Bemerkung"), validators=[Optional()])
    submit = SubmitField(_("Anfrage senden"))


# ---------------------------------------------------------------------------
# Teilnehmer: eigene Angaben
# ---------------------------------------------------------------------------

class ProfileForm(FlaskForm):
    first_name = StringField(_("Vorname"), validators=[DataRequired(), Length(max=100)])
    last_name = StringField(_("Nachname"), validators=[DataRequired(), Length(max=100)])
    phone = StringField(_("Telefon"), validators=[Optional(), Length(max=50)])
    # Verein des Läufers (pro Läufer). choices werden in der Route gesetzt;
    # 0 = kein Verein.
    club_id = SelectField(_("Verein"), coerce=int, validators=[Optional()])
    # Franz. Zusatzangaben (nur relevant fuer Teilnehmer mit auslaendischer Lizenz,
    # fuers offizielle CNEAC-Ergebnisformular). Alle optional.
    fr_license_no = StringField(_("N° licence (franz. Läuferlizenz)"), validators=[Optional(), Length(max=50)])
    fr_club = StringField(_("Club (franz. Verein)"), validators=[Optional(), Length(max=120)])
    fr_regionale = StringField(_("Régionale"), validators=[Optional(), Length(max=120)])
    submit = SubmitField(_("Speichern"))


class HandlerForm(FlaskForm):
    """Weiterer Läufer/Hundeführer, den ein Konto verwaltet (z.B. Familie mit
    gemeinsamer Mailadresse)."""
    first_name = StringField(_("Vorname"), validators=[DataRequired(), Length(max=100)])
    last_name = StringField(_("Nachname"), validators=[DataRequired(), Length(max=100)])
    phone = StringField(_("Telefon"), validators=[Optional(), Length(max=50)])
    club_id = SelectField(_("Verein"), coerce=int, validators=[Optional()])
    fr_license_no = StringField(_("N° licence (franz. Läuferlizenz)"), validators=[Optional(), Length(max=50)])
    fr_club = StringField(_("Club (franz. Verein)"), validators=[Optional(), Length(max=120)])
    fr_regionale = StringField(_("Régionale"), validators=[Optional(), Length(max=120)])
    submit = SubmitField(_("Läufer speichern"))


# ---------------------------------------------------------------------------
# Teilnehmer: Hunde & Anmeldung
# ---------------------------------------------------------------------------

class DogForm(FlaskForm):
    name = StringField(_("Hundename"), validators=[DataRequired(), Length(max=120)])
    breed = StringField(_("Rasse"), validators=[Optional(), Length(max=120)])
    # Geschlecht ist eine allgemeine Hunde-Eigenschaft (fuer alle Laender), nicht
    # mehr nur FR. Wird ins Event-Paket exportiert (sexe).
    sex = SelectField(_("Geschlecht"), choices=[("", "—"), ("M", _("Rüde (M)")), ("F", _("Hündin (F)"))], validators=[Optional()])
    # Lizenz-Typ bestimmt gleichzeitig das Land: CH, oder auslaendisch mit
    # laenderspezifischen Zusatzfeldern (FRA=CNEAC, DEU=VDH) bzw. ein anderes
    # Ausland. Der eigentliche DB-Enum kennt nur CH/FOREIGN — das Mapping passiert
    # in der Route; das Landeskuerzel landet im Lizenz-Praefix (FRA-/DEU-).
    license_kind = SelectField(
        _("Lizenz-Typ"),
        choices=[
            ("CH", _("Schweiz (CH)")),
            ("FRA", _("Frankreich (FRA) – CNEAC")),
            ("DEU", _("Deutschland (GER) – VDH")),
            ("FOREIGN", _("Ausland (anderes Land)")),
        ],
    )
    license_no = StringField(_("Lizenznummer"), validators=[DataRequired(), Length(max=50)])
    # SHSB = Stammbuch-Nummer (Schweiz. Hundestammbuch). Schweizer Angabe, nur
    # beim CH-Typ sichtbar. Optional, meist nur bei Zuchthunden.
    shsb = StringField(_("SHSB-Nr."), validators=[Optional(), Length(max=50)])
    # FAPAC = franz. Hundelizenz. Nur beim FRA-Typ relevant (CNEAC-Formular).
    fapac_no = StringField(_("FAPAC (franz. Hundelizenz)"), validators=[Optional(), Length(max=50)])
    # Dt. VDH-Leistungsbuchnummer. Nur beim DEU-Typ relevant (VDH-Auslandsergebnis).
    leistungsbuch_no = StringField(_("Leistungsbuch-Nr. (VDH)"), validators=[Optional(), Length(max=50)])
    # Chip-/Transpondernummer (optional, allgemein). U.a. fürs deutsche VDH-Formular.
    microchip = StringField(_("Chip-Nr."), validators=[Optional(), Length(max=50)])
    submit = SubmitField(_("Hund speichern"))


class DogDetailsForm(FlaskForm):
    """Name/Rasse nachtraeglich korrigieren – nur fuer den Besitzer (OWNER),
    nicht fuer blosse Hundefuehrer."""
    name = StringField(_("Hundename"), validators=[DataRequired(), Length(max=120)])
    breed = StringField(_("Rasse"), validators=[Optional(), Length(max=120)])
    submit = SubmitField(_("Speichern"))


class DogClassForm(FlaskForm):
    category = SelectField(
        _("Kategorie"),
        choices=[("L", _("Large (L)")), ("I", _("Intermediate (I)")), ("M", _("Medium (M)")), ("S", _("Small (S)"))],
    )
    class_level = SelectField(
        _("Klasse"),
        choices=[("1", _("Klasse 1")), ("2", _("Klasse 2")), ("3", _("Klasse 3"))],
        coerce=int,
    )
    submit = SubmitField(_("Speichern"))


class EventRegistrationForm(FlaskForm):
    dog_id = SelectField(_("Hund"), coerce=int)
    # Läufer/Hundeführer der Anmeldung — ein Konto kann mehrere Läufer verwalten.
    # choices werden in der Route gesetzt (alle Läufer des Kontos). validate_choice
    # aus: das Feld wird bei nur 1 Läufer gar nicht gerendert (dann nicht gepostet),
    # und die Zugehörigkeit prüft die Route ohnehin selbst (Fallback eigene Person).
    handler_id = SelectField(_("Hundeführer"), coerce=int, validators=[Optional()],
                             validate_choice=False)
    class_level = SelectField(_("Klasse"), choices=[("1", _("Klasse 1")), ("2", _("Klasse 2")), ("3", _("Klasse 3"))], coerce=int)
    is_in_season = BooleanField(_("Hündin ist läufig"))
    submit = SubmitField(_("Anmelden"))
