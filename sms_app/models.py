from django.db import models
from django.contrib.auth.models import AbstractUser
from django.utils import timezone
import random
import string

class SenderID(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    username = models.CharField(max_length=255, unique=True)
    password = models.CharField(max_length=255)
    sender_id = models.CharField(max_length=255)
    token = models.TextField()
    refresh_token = models.TextField()
    token_updated_date = models.DateTimeField()

    def __str__(self):
        return self.username

    class Meta:
        verbose_name_plural = "Sender IDs"

class CustomUser(AbstractUser):
    created_at = models.DateTimeField(auto_now_add=True)
    email = models.EmailField(unique=True)
    phone_number = models.CharField(max_length=13)
    sender_id = models.ForeignKey(SenderID, on_delete=models.CASCADE, null=True, blank=True)
    failed_login_attempts = models.IntegerField(default=0)
    last_failed_attempt = models.DateTimeField(null=True, blank=True)
    locked_until = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return self.username

class Account(models.Model):
    account_number = models.CharField(max_length=16)
    account_holder_name = models.CharField(max_length=255)
    account_id = models.CharField(max_length=255, unique=True)
    gui_balance = models.DecimalField(max_digits=12, decimal_places=4)
    api_balance = models.DecimalField(max_digits=12, decimal_places=4)
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE)

    def __str__(self):
        return f"{self.account_holder_name} - {self.account_number}"

class CoinHistory(models.Model):
    CATEGORY_CHOICES = [
        ('api_balance', 'API Balance'),
        ('gui_balance', 'GUI Balance')
    ]

    TRANSACTION_TYPE_CHOICES = [
        ('credit', 'Credit'),
        ('debit', 'Debit'),
    ]

    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE)
    coins = models.DecimalField(max_digits=12, decimal_places=4)
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES)
    reason = models.TextField()
    transaction_id = models.CharField(max_length=16, unique=True)
    transaction_type = models.CharField(max_length=6, choices=TRANSACTION_TYPE_CHOICES)
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if not self.transaction_id:
            self.transaction_id = ''.join(random.choices(string.ascii_letters + string.digits, k=16))
        super(CoinHistory, self).save(*args, **kwargs)

    def __str__(self):
        return f"Transaction {self.transaction_id} - {self.user.username}"


class CampaignDetails(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE)
    campaign_id = models.CharField(max_length=12, unique=True)
    campaign_name = models.CharField(max_length=60)
    msg_type = models.CharField(max_length=1)
    request_type = models.CharField(max_length=1)
    receiver = models.JSONField()  # To store list of receivers
    content = models.TextField()

class ReportDetails(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE)
    campaign_id = models.CharField(max_length=12)
    report_id = models.CharField(max_length=12, unique=True)
    status = models.CharField(max_length=20)
    description = models.TextField()
    msgCount = models.IntegerField()
    errorCode = models.IntegerField()
    messageId = models.CharField(max_length=255)
    receiver = models.JSONField()  
    
    def __str__(self):
        return f"Report {self.report_id} - Status: {self.status}"