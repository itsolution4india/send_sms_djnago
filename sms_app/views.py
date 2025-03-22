from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib import messages
from django.utils import timezone
from datetime import timedelta
from django.contrib.auth.decorators import login_required
from .models import CustomUser, CoinHistory, Account, SMSLog
from .forms import CoinHistoryForm
from django.core.paginator import Paginator
import requests
from django.http import JsonResponse

def login_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
        
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        
        try:
            user = CustomUser.objects.get(username=username)
            
            # Check if account is locked
            if user.locked_until and user.locked_until > timezone.now():
                remaining_time = user.locked_until - timezone.now()
                if remaining_time > timedelta(minutes=25):
                    # 30 minute lockout
                    minutes = int(remaining_time.total_seconds() // 60)
                    messages.error(request, f'Account locked. Try again after {minutes} minutes.')
                else:
                    # 1 minute lockout
                    seconds = int(remaining_time.total_seconds())
                    messages.error(request, f'Account locked. Try again after {seconds} seconds.')
                return render(request, 'login.html')
            
            # Try to authenticate
            user_auth = authenticate(request, username=username, password=password)
            
            if user_auth is not None:
                # Reset failed attempts on successful login
                user.failed_login_attempts = 0
                user.last_failed_attempt = None
                user.locked_until = None
                user.save()
                
                login(request, user_auth)
                return redirect('dashboard')
            else:
                # Increment failed attempts
                user.failed_login_attempts += 1
                user.last_failed_attempt = timezone.now()
                
                # Check for lockout conditions
                if user.failed_login_attempts >= 3:
                    if user.failed_login_attempts >= 6:
                        # Lock for 30 minutes after 6 attempts (3 + 3)
                        user.locked_until = timezone.now() + timedelta(minutes=30)
                        user.failed_login_attempts = 0
                        messages.error(request, 'Too many failed attempts. Account locked for 30 minutes.')
                    else:
                        # Lock for 1 minute after 3 attempts
                        user.locked_until = timezone.now() + timedelta(minutes=1)
                        messages.error(request, 'Too many failed attempts. Account locked for 1 minute.')
                else:
                    messages.error(request, 'Invalid username or password.')
                
                user.save()
                
        except CustomUser.DoesNotExist:
            messages.error(request, 'Invalid username or password.')
        
    return render(request, 'login.html')

@login_required
def dashboard_view(request):
    return render(request, 'dashboard.html')

@login_required
def logout_view(request):
    logout(request)
    return redirect('login')

def admin_view(request):
    if request.method == 'POST':
        form = CoinHistoryForm(request.POST)
        if form.is_valid():
            coin_history = form.save(commit=False)

            # Assign the user field here, assuming request.user is the user making the transaction
            coin_history.user = request.user

            account = Account.objects.filter(user=coin_history.user).first()

            if not account:
                messages.error(request, f"No account found for user {coin_history.user.username}.")
                return redirect('admin_view')

            if coin_history.category == 'api_balance':
                balance = account.api_balance
            else:
                balance = account.gui_balance

            if coin_history.transaction_type == 'credit':
                # Credit coins to the account balance
                new_balance = balance + coin_history.coins
                reason = f"{coin_history.coins} coins have been credited to your account for {dict(CoinHistory.CATEGORY_CHOICES)[coin_history.category]}"
            else:
                # Debit coins from the account balance
                if balance >= coin_history.coins:
                    new_balance = balance - coin_history.coins
                    reason = f"{coin_history.coins} coins have been debited from your account for {dict(CoinHistory.CATEGORY_CHOICES)[coin_history.category]}"
                else:
                    messages.error(request, f"Insufficient balance to debit {coin_history.coins} coins.")
                    return redirect('admin_view')

            # Update the account balance
            if coin_history.category == 'api_balance':
                account.api_balance = new_balance
            else:
                account.gui_balance = new_balance

            account.save()

            # Generate the reason automatically
            coin_history.reason = reason

            # Save coin history
            coin_history.save()

            messages.success(request, f"Transaction {coin_history.transaction_id} successfully recorded!")
            return redirect('admin_view')

    else:
        form = CoinHistoryForm()

    return render(request, 'admin_view.html', {'form': form})


def billing_view(request):
    user = request.user
    transactions = None
    account = None

    try:
        account = Account.objects.get(user=user)
    except Account.DoesNotExist:
        account = None
        messages.error(request, "No account found for the current user.")

    transactions = CoinHistory.objects.filter(user=user).order_by('-created_at')

    paginator = Paginator(transactions, 10)
    page_number = request.GET.get('page')
    transactions = paginator.get_page(page_number)

    return render(request, 'billing.html', {'transactions': transactions, 'account': account})


def send_sms(request):
    if request.method == 'POST':
        receiver = request.POST.get('receiver')
        message = request.POST.get('message')

        url = "https://api.mobireach.com.bd/sms/send"
        headers = {
            'Content-Type': 'application/json',
            'Authorization': 'Bearer refresh_token',
        }
        data = {
            "sender": "adaReach",
            "receiver": [receiver],
            "contentType": 1,
            "content": message,
            "msgType": "T",
            "requestType": "S"
        }

        response = requests.post(url, headers=headers, json=data)
        
        if response.status_code == 200:
            return JsonResponse({"success": True, "message": "SMS sent successfully!"})
        else:
            return JsonResponse({"success": False, "message": "Failed to send SMS"})

    return render(request, 'send_sms.html')

@login_required
def sms_logs(request):
    logs = SMSLog.objects.filter(user=request.user).order_by('-created_at')
    return render(request, 'sms_app/sms_logs.html', {'logs': logs})