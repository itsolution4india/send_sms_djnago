import logging
import os
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
import requests
import logging
from datetime import datetime, timedelta
from django.utils import timezone
import logging

logger = logging.getLogger('sms_app_logger')

scheduler = None

def refresh_sender_id_tokens():
    """
    Check all SenderID objects and refresh tokens that are older than 10 minutes.
    """
    from .models import SenderID
    
    logger.info("Starting token refresh check for all SenderIDs")
    
    # Get all SenderID objects
    sender_ids = SenderID.objects.all()
    
    if not sender_ids:
        logger.info("No SenderID objects found in database")
        return
    
    current_time = timezone.now()
    refresh_threshold = timedelta(minutes=10)
    
    for sender in sender_ids:
        # Check if token needs refreshing
        time_since_update = current_time - sender.token_updated_date
        
        if time_since_update < refresh_threshold:
            logger.debug(f"Skipping refresh for {sender.username} - token is still fresh")
            continue
        
        logger.info(f"Refreshing token for {sender.username} (last updated: {sender.token_updated_date})")
        
        # Try refresh token first
        if refresh_token_api(sender):
            logger.info(f"Successfully refreshed token for {sender.username} using refresh token")
        else:
            # If refresh fails, try login with username/password
            logger.warning(f"Refresh token failed for {sender.username}, attempting login with credentials")
            if login_with_credentials(sender):
                logger.info(f"Successfully refreshed token for {sender.username} using credentials")
            else:
                logger.error(f"Failed to refresh token for {sender.username} - both methods failed")
    
    logger.info("Token refresh check completed")

def refresh_token_api(sender):
    """
    Try to refresh the token using the refresh token.
    Returns True if successful, False otherwise.
    """
    try:
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {sender.refresh_token}'
        }
        
        response = requests.post(
            'https://api.mobireach.com.bd/auth/token/refresh',
            headers=headers
        )
        
        if response.status_code == 200:
            data = response.json()
            
            # Update the model with new tokens
            sender.token = data['token']
            sender.refresh_token = data['refresh_token']
            sender.token_updated_date = timezone.now()
            sender.save()
            
            return True
        else:
            logger.warning(f"Refresh token API failed with status code {response.status_code}")
            return False
            
    except Exception as e:
        logger.error(f"Exception during token refresh: {str(e)}")
        return False

def login_with_credentials(sender):
    """
    Try to get new tokens using username and password.
    Returns True if successful, False otherwise.
    """
    try:
        headers = {
            'Content-Type': 'application/json'
        }
        
        payload = {
            'username': sender.username,
            'password': sender.password
        }
        
        response = requests.post(
            'https://api.mobireach.com.bd/auth/tokens',
            headers=headers,
            json=payload
        )
        
        if response.status_code == 200:
            data = response.json()
            
            # Update the model with new tokens
            sender.token = data['token']
            sender.refresh_token = data['refresh_token']
            sender.token_updated_date = timezone.now()
            sender.save()
            
            return True
        else:
            logger.error(f"Login API failed with status code {response.status_code}")
            return False
            
    except Exception as e:
        logger.error(f"Exception during login: {str(e)}")
        return False

def scheduled_task():
    """
    Replace the original scheduled task to run token refresh.
    """
    logger.info("Scheduler running token refresh task")
    refresh_sender_id_tokens()

def start_scheduler():
    global scheduler
    if os.environ.get('RUN_MAIN') == 'true':
        if scheduler is None:
            scheduler = BackgroundScheduler()
            scheduler.add_job(scheduled_task, IntervalTrigger(minutes=10))
            scheduler.start()
            logger.info("Scheduler started successfully.")
