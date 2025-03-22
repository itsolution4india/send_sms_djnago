import os
import sys
import threading

def main():
    """Run administrative tasks."""
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'send_sms.settings')
    try:
        from django.core.management import execute_from_command_line
        from sms_app.scheduler import start_scheduler

        if 'runserver' in sys.argv and os.environ.get('RUN_MAIN') == 'true':
            threading.Thread(target=start_scheduler, daemon=True).start()
            print("Scheduler started in a separate thread.")

    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc
    execute_from_command_line(sys.argv)

if __name__ == '__main__':
    main()
