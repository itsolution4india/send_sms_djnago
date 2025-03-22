from django.apps import AppConfig
import threading
from sms_app.scheduler import start_scheduler

class SmsAppConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'sms_app'

    def ready(self):
        if not hasattr(threading.current_thread(), '_scheduler_started'):
            threading.current_thread()._scheduler_started = True
            start_scheduler()
