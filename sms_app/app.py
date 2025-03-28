from django.apps import AppConfig
import os
from .utils import logger

class SmsappConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'sms_app'

    def ready(self):
        if os.environ.get('DJANGO_SETTINGS_MODULE') == 'sms_app.settings':
            try:
                logger.info("Scheduler initialized in ready method.")
            except Exception as e:
                logger.error(f"Error while starting the scheduler: {str(e)}")
