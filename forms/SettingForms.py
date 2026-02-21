from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField, SelectField, IntegerField
from wtforms.validators import DataRequired, Optional, NumberRange

# Голоса для ru-RU по https://yandex.cloud/ru/docs/speechkit/tts/voices
# v1,v3: alena, filipp, ermil, jane, omazh, zahar, marina, madi_ru
# v3 only: dasha, julia, lera, masha, alexander, kirill, anton, saule_ru, zamira_ru, zhanar_ru, yulduz_ru
V1_VOICES = ['alena', 'filipp', 'ermil', 'jane', 'omazh', 'zahar', 'marina', 'madi_ru']

# Амплуа (роли) для каждого голоса
VOICE_EMOTIONS = {
    'alena': ['neutral', 'good'],
    'filipp': ['neutral'],
    'ermil': ['neutral', 'good'],
    'jane': ['neutral', 'good', 'evil'],
    'omazh': ['neutral', 'evil'],
    'zahar': ['neutral', 'good'],
    'marina': ['neutral', 'whisper', 'friendly'],
    'madi_ru': ['neutral'],
    'dasha': ['neutral', 'good', 'friendly'],
    'julia': ['neutral', 'strict'],
    'lera': ['neutral', 'friendly'],
    'masha': ['good', 'strict', 'friendly'],
    'alexander': ['neutral', 'good'],
    'kirill': ['neutral', 'strict', 'good'],
    'anton': ['neutral', 'good'],
    'saule_ru': ['neutral', 'strict', 'whisper'],
    'zamira_ru': ['neutral', 'strict', 'friendly'],
    'zhanar_ru': ['neutral', 'strict', 'friendly'],
    'yulduz_ru': ['neutral', 'strict', 'friendly', 'whisper'],
}

SPEAKER_CHOICES = [
    ('marina', 'marina (F, default)'),
    ('alena', 'alena (F)'),
    ('dasha', 'dasha (F)'),
    ('jane', 'jane (F)'),
    ('julia', 'julia (F)'),
    ('lera', 'lera (F)'),
    ('masha', 'masha (F)'),
    ('omazh', 'omazh (F)'),
    ('saule_ru', 'saule_ru (F)'),
    ('zamira_ru', 'zamira_ru (F)'),
    ('zhanar_ru', 'zhanar_ru (F)'),
    ('yulduz_ru', 'yulduz_ru (F)'),
    ('alexander', 'alexander (M)'),
    ('anton', 'anton (M)'),
    ('ermil', 'ermil (M)'),
    ('filipp', 'filipp (M)'),
    ('kirill', 'kirill (M)'),
    ('madi_ru', 'madi_ru (M)'),
    ('zahar', 'zahar (M)'),
]

# Амплуа (роли) голосов: neutral, good, evil, friendly, strict, whisper
EMOTION_CHOICES = [
    ('neutral', 'neutral (neutral)'),
    ('good', 'good (joyful)'),
    ('evil', 'evil (irritated)'),
    ('friendly', 'friendly'),
    ('strict', 'strict'),
    ('whisper', 'whisper'),
]


class SettingsForm(FlaskForm):
    access_key = StringField('Access Key', validators=[DataRequired()])
    api_version = SelectField('API Version', validators=[DataRequired()], choices=[('v1', 'API v1'), ('v3', 'API v3')])
    speaker = SelectField('Speaker', validators=[DataRequired()], choices=SPEAKER_CHOICES)
    emotion = SelectField('Emotion', validators=[DataRequired()], choices=EMOTION_CHOICES)
    default_volume = IntegerField('Default volume', validators=[Optional(), NumberRange(min=0, max=100)])
    submit = SubmitField('Submit')