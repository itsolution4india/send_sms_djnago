from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib import messages
from django.utils import timezone
from datetime import timedelta
from django.contrib.auth.decorators import login_required
from .models import CustomUser, CoinHistory, Account, CampaignDetails, ReportDetails, SendSmsApiResponse, Webhook, ApiCredentials, MessageStatus
from .forms import CoinHistoryForm, WebhookForm
import csv
from django.utils.dateparse import parse_date
from django.db import IntegrityError
import secrets
from django.views.decorators.http import require_http_methods
from django.views import View
from django.core.paginator import Paginator
import requests
from django.http import JsonResponse
import random, string
from django.db.models import Q
from django.http import HttpResponse
from datetime import datetime, timedelta
from django.db.models import Count, Sum
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db.models.functions import TruncDate
from .utils import logger,check_user_permission

def admin_check(user):
    return user.is_superuser

def login_view(request):
    if request.user.is_authenticated:
        logger.info(f"User logged in successfully {request.user}")
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

@user_passes_test(admin_check, login_url='/login/')
def admin_view(request):
    coin_history = None
    form = CoinHistoryForm()

    # Handle POST (new transaction)
    if request.method == 'POST':
        form = CoinHistoryForm(request.POST)
        if form.is_valid():
            coin_history = form.save(commit=False)
            selected_user = coin_history.user

            # Ensure account exists
            try:
                # Ensure account exists (with 'get_or_create' to avoid duplicates)
                # Adding account_id default as 0 for creating the account if it's missing
                account, created = Account.objects.get_or_create(
                    user=selected_user,
                    defaults={'gui_balance': 0, 'api_balance': 0, 'account_id': 0}  # Ensuring account_id is set
                )

                if created:
              
                    if not account.account_id:
                        raise IntegrityError("Account ID is required in the backend.")

            except IntegrityError as e:
             
                if 'account_id' in str(e):
                    messages.error(request, "Account ID is missing. Please make sure it's added in the backend.")
                else:
                    messages.error(request, "An account already exists for this user.")
                return redirect('admin_view')

            # Determine balance
            balance = account.api_balance if coin_history.category == 'api_balance' else account.gui_balance

            # Credit or debit logic
            if coin_history.transaction_type == 'credit':
                new_balance = balance + coin_history.coins
                reason = f"{coin_history.coins} coins have been credited to your account for {dict(CoinHistory.CATEGORY_CHOICES).get(coin_history.category)}"
            else:
                if balance >= coin_history.coins:
                    new_balance = balance - coin_history.coins
                    reason = f"{coin_history.coins} coins have been debited from your account for {dict(CoinHistory.CATEGORY_CHOICES).get(coin_history.category)}"
                else:
                    messages.error(request, f"Insufficient balance to debit {coin_history.coins} coins.")
                    return redirect('admin_view')

            # Update balance
            if coin_history.category == 'api_balance':
                account.api_balance = new_balance
            else:
                account.gui_balance = new_balance
            account.save()

            # Save transaction
            coin_history.reason = reason
            coin_history.save()

            messages.success(request, f"Transaction {coin_history.transaction_id} successfully recorded!")
            return redirect('admin_view')

    # Handle GET: Filtering
    coin_history_qs = CoinHistory.objects.all().order_by('-created_at')

    txn_type = request.GET.get('transaction_type')
    category_filter = request.GET.get('category')
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')
    trans_id=request.GET.get('trans_id')
    username=request.GET.get('user')

    if txn_type:
        coin_history_qs = coin_history_qs.filter(transaction_type=txn_type)

    if category_filter:
        coin_history_qs = coin_history_qs.filter(category=category_filter)

    if start_date:
        coin_history_qs = coin_history_qs.filter(created_at__date__gte=parse_date(start_date))

    if end_date:
        coin_history_qs = coin_history_qs.filter(created_at__date__lte=parse_date(end_date))
    if trans_id:
        coin_history_qs = coin_history_qs.filter(transaction_id__icontains=trans_id)

    if username:
        coin_history_qs=coin_history_qs.filter(user__username=username)
    users = CustomUser.objects.all()

    return render(request, 'admin_view.html', {
        'form': form,
        'coin_history': coin_history_qs,
        'users': users,
         'types': CoinHistory.TRANSACTION_TYPE_CHOICES,
        'categories': CoinHistory.CATEGORY_CHOICES,
        'txn_type': txn_type,
        'category_filter': category_filter,
        'start_date': start_date,
        'end_date': end_date,
    })



@login_required
def billing_view(request):
    user = request.user
    transactions = None
    account = None
    if not check_user_permission(request.user, 'can_see_billing'):
           return redirect("access_denide")

    try:
        account = Account.objects.get(user=user)
    except Account.DoesNotExist:
        account = None
        messages.error(request, "No account found for the current user.")

    transactions = CoinHistory.objects.filter(user=user).order_by('-created_at')

    paginator = Paginator(transactions, 10)
    page_number = request.GET.get('page')
    transactions = paginator.get_page(page_number)

    return render(request, 'billing.html', {'transactions': transactions, 'account': account, "user": user})


class SendSMSView(LoginRequiredMixin, View):
    login_url = '/login/'
    redirect_field_name = 'redirect_to'
    
    def get(self, request):
        if not check_user_permission(request.user, 'can_start_campaign'):
           return redirect("access_denide")
        return render(request, 'send_sms.html')

    def post(self, request):
        campaign_name = request.POST.get('campaignName')
        msg_type = request.POST.get('msgType')
        request_type = request.POST.get('requestType')
        receiver = request.POST.get('receiver')
        content = request.POST.get('content')
        csv_file = request.FILES.get('csv_file')

        current_user = request.user
        if current_user.sender_id:
            sender_info = current_user.sender_id
        else:
            sender_info = None
        
        # Process CSV file if uploaded
        if csv_file:
            csv_reader = csv.DictReader(csv_file.read().decode('utf-8').splitlines())
            receiver_list = []
            for row in csv_reader:
                # Convert scientific notation to integer and ensure it's in proper phone number format
                phone_number = row['Phone_numbers']
                try:
                    # Handle scientific notation and strip any unwanted characters
                    phone_number = str(int(float(phone_number)))
                    receiver_list.append(phone_number)
                except ValueError:
                    # Handle invalid phone number formats
                    print(f"Invalid phone number format: {phone_number}")
                    messages.error(request, f"Invalid phone number format: {phone_number}")
                    return redirect('send_sms')
            print(receiver_list)
        else:
            receiver_list = [receiver]

        # Create and save Campaign Details
        campaign_id = ''.join(random.choices(string.ascii_letters + string.digits, k=12))

        # Prepare payload for FastAPI
        payload = {
            "sender": sender_info.sender_id,
            "token": sender_info.token,
            "receiver": receiver_list,
            "msgType": msg_type,
            "requestType": request_type,
            "content": content,
            "campaign_id": campaign_id,
            "user_id": current_user.id
        }
        
        print(payload)
        url = "https://api.wtsdealnow.com/send_sms"
        headers = {
            'Authorization': f'Bearer {sender_info.token}',
            'Content-Type': 'application/json'
        }

        # Send SMS and handle response
        response = requests.post(url, json=payload, headers=headers)
        print(response.json())
        if response.status_code == 200:
            try:
                campaign = CampaignDetails.objects.create(
                    created_at=timezone.now(),
                    user=request.user,
                    campaign_id=campaign_id,
                    campaign_name= campaign_name,
                    msg_type=msg_type,
                    request_type=request_type,
                    receiver=receiver_list,
                    content=content
                )
            except Exception as e:
                print(e)
            api_response = response.json()
            total_receivers = len(receiver_list)

            # Deduct coins based on the number of receivers
            account = Account.objects.filter(user=request.user).first()
            if account and account.gui_balance >= total_receivers:
                new_balance = account.gui_balance - total_receivers
                account.gui_balance = new_balance
                account.save()

                # Save CoinHistory
                CoinHistory.objects.create(
                    user=request.user,
                    coins=total_receivers,
                    category='gui_balance',
                    reason=f"Sent SMS to {total_receivers} receivers.",
                    transaction_type='debit'
                )

                messages.success(request, "SMS sent successfully!")
            else:
                messages.error(request, "Insufficient balance to send SMS.")
        else:
            messages.error(request, "Failed to send SMS: " + response.text)

        return redirect('send_sms')

# Show the reports
@login_required
def report_view(request):
    if not check_user_permission(request.user, 'can_view_reports'):
           return redirect("access_denide")
    reports = ReportDetails.objects.filter(user=request.user)

    # Date filtering
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')
    search_query = request.GET.get('search', '')

    if start_date:
        reports = reports.filter(created_at__gte=start_date)
    if end_date:
        reports = reports.filter(created_at__lte=end_date)
    
    # Search filtering
    if search_query:
        reports = reports.filter(
            Q(campaign_id__icontains=search_query) |
            Q(status__icontains=search_query) |
            Q(description__icontains=search_query)
        )

    # Pagination
    paginator = Paginator(reports, 10)  # 10 records per page
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    return render(request, 'report_details.html', {
        'page_obj': page_obj, 
        'start_date': start_date, 
        'end_date': end_date, 
        'search_query': search_query
    })

# Delete a report
@login_required
def delete_report(request):
    if request.method == 'POST':
        report_id = request.POST.get('report_id')
        report = get_object_or_404(ReportDetails, id=report_id)
        report.delete()
        return JsonResponse({'status': 'success'})
    return JsonResponse({'status': 'error'}, status=400)

# Fetch the latest report details
@login_required
def fetch_latest_report(request):
    current_user = request.user
    if current_user.sender_id:
        sender_info = current_user.sender_id
        token = sender_info.token
    else:
        token = None
    if request.method == 'POST':
        report_id = request.POST.get('report_id')
        message_id = request.POST.get('message_id')
        receiver = request.POST.get('receiver')

        # API call to fetch the latest details
        url = f"https://api.mobireach.com.bd/sms/status?sender=adaXXX&messageId={message_id}&receiver={receiver}"
        headers = {
            'Authorization': f'Bearer {token}'
        }
        response = requests.get(url, headers=headers)
        print(response.json())
        if response.status_code == 200:
            messages.success(request, "Report refreshed successfully ")
            data = response.json()

            # Update the report details in the database
            report = get_object_or_404(ReportDetails, id=report_id)
            report.status = data.get('status', report.status)
            report.description = data.get('description', report.description)
            report.msgCount = data.get('msgCount', report.msgCount)
            report.errorCode = data.get('errorCode', report.errorCode)
            report.save()

            # Return updated details to the frontend
            return redirect('report_view')
        else:
            messages.error(request, "Failed to refresh report")
            return redirect('report_view')


@login_required
def profile_view(request):
    """
    View to display user profile information including account details.
    Requires user to be logged in.
    """
    user = request.user
    try:
        # Get the account related to the logged-in user
        account = Account.objects.get(user=user)
        
        # Get the first letter of account holder name for the logo
        first_letter = account.account_holder_name[0].upper() if account.account_holder_name else user.username[0].upper()
        
        context = {
            'user': user,
            'account': account,
            'first_letter': first_letter,
        }
        return render(request, 'profile.html', context)
    except Account.DoesNotExist:
        # Handle case where user doesn't have an account
        first_letter = user.username[0].upper()
        context = {
            'user': user,
            'first_letter': first_letter,
            'no_account': True
        }
        return render(request, 'profile.html', context)
    
@login_required
def api_documentation(request):
    if not check_user_permission(request.user, 'can_sms_api_reports'):
        return redirect("access_denide")
    
    user=CustomUser.objects.get(email=request.user.email)
    api_token=ApiCredentials.objects.get(user=request.user).token
    context={
        'username':user.username,
        'senderId':user.sender_id.sender_id,
        'apitoken':api_token
    }
     
    return render(request, 'api_documentation.html',context)

@login_required   
def download_report_csv(request):
    # Get the report ID from the request
    report_id = request.GET.get('report_id')
    
    # Initialize response
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="report_{report_id}.csv"'
    
    # Create CSV writer
    writer = csv.writer(response)
    
    # Write header row
    writer.writerow([
        'Created At', 'Campaign ID', 'Campaign Name', 'Message Type', 
        'Request Type', 'Receiver', 'Content', 'Status', 'Message Count', 
        'Error Code', 'Message ID'
    ])
    
    # Fetch report details
    report = ReportDetails.objects.get(id=report_id)
    
    # Fetch associated campaign details
    try:
        campaign = CampaignDetails.objects.get(campaign_id=report.campaign_id)
        campaign_name = campaign.campaign_name
        msg_type = campaign.msg_type
        request_type = campaign.request_type
        content = campaign.content
    except CampaignDetails.DoesNotExist:
        campaign_name = "N/A"
        msg_type = "N/A"
        request_type = "N/A"
        content = "N/A"
    
    # Write a row for each receiver
    if isinstance(report.receiver, list):
        for receiver in report.receiver:
            writer.writerow([
                report.created_at,
                report.campaign_id,
                campaign_name,
                msg_type,
                request_type,
                receiver,
                content,
                report.status,
                1,
                report.errorCode,
                report.messageId
            ])
    else:
        # If receiver is not a list (handling edge cases)
        writer.writerow([
            report.created_at,
            report.campaign_id,
            campaign_name,
            msg_type,
            request_type,
            report.receiver,
            content,
            report.status,
            1,
            report.errorCode,
            report.messageId
        ])
    
    return response

@login_required
def download_all_reports_csv(request):
    """Download all reports that match the current filter criteria"""
    # Get filter parameters
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')
    search_query = request.GET.get('search', '')
    
    # Get all reports based on filter
    reports = ReportDetails.objects.all()
    
    if start_date:
        reports = reports.filter(created_at__gte=start_date)
    if end_date:
        reports = reports.filter(created_at__lte=end_date)
    
    if search_query:
        reports = reports.filter(
            Q(campaign_id__icontains=search_query) |
            Q(status__icontains=search_query) |
            Q(description__icontains=search_query)
        )
    
    # Initialize response
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="all_reports.csv"'
    
    # Create CSV writer
    writer = csv.writer(response)
    
    # Write header row
    writer.writerow([
        'Created At', 'Campaign ID', 'Campaign Name', 'Message Type', 
        'Request Type', 'Receiver', 'Content', 'Status', 'Message Count', 
        'Error Code', 'Message ID'
    ])
    
    # Write data rows
    for report in reports:
        # Fetch associated campaign details
        try:
            campaign = CampaignDetails.objects.get(campaign_id=report.campaign_id)
            campaign_name = campaign.campaign_name
            msg_type = campaign.msg_type
            request_type = campaign.request_type
            content = campaign.content
        except CampaignDetails.DoesNotExist:
            campaign_name = "N/A"
            msg_type = "N/A"
            request_type = "N/A"
            content = "N/A"
        
        # Write a row for each receiver
        if isinstance(report.receiver, list):
            for receiver in report.receiver:
                writer.writerow([
                    report.created_at,
                    report.campaign_id,
                    campaign_name,
                    msg_type,
                    request_type,
                    receiver,
                    content,
                    report.status,
                    report.msgCount,
                    report.errorCode,
                    report.messageId
                ])
        else:
            # If receiver is not a list (handling edge cases)
            writer.writerow([
                report.created_at,
                report.campaign_id,
                campaign_name,
                msg_type,
                request_type,
                report.receiver,
                content,
                report.status,
                report.msgCount,
                report.errorCode,
                report.messageId
            ])
    
    return response

@login_required
def sms_api_report(request):
    # Default to last 30 days if no date range specified
    if not check_user_permission(request.user, 'can_sms_api_reports'):
           return redirect("access_denide")
    end_date = request.GET.get('end_date')
    start_date = request.GET.get('start_date')
    
    # Convert string dates to datetime objects
    try:
        end_date = datetime.strptime(end_date, '%Y-%m-%d').date() if end_date else datetime.now().date()
        start_date = datetime.strptime(start_date, '%Y-%m-%d').date() if start_date else (end_date - timedelta(days=30))
    except (ValueError, TypeError):
        # Fallback to default dates if parsing fails
        end_date = datetime.now().date()
        start_date = end_date - timedelta(days=30)
    
    # Filter queryset based on date range
    queryset = SendSmsApiResponse.objects.filter(
        created_at__date__range=[start_date, end_date],
        user=request.user
    )
    
    # Calculate total error codes by counting non-zero error codes
    total_error_codes = queryset.exclude(errorCode=0).count()
    
    # Calculate statistics
    promotional_sms_count = queryset.filter(msg_type='P').aggregate(total_promotional_sms=Sum('user_msgCount'))['total_promotional_sms'] or 0
    transactional_sms_count = queryset.filter(msg_type='T').aggregate(total_transactional_sms=Sum('user_msgCount'))['total_transactional_sms'] or 0
    stats = {
        'campaign_name': 'API V2 Service',
        'status': 'Running',
        'total_error_code': total_error_codes,
        'sms_count': queryset.aggregate(total_sms=Sum('user_msgCount'))['total_sms'] or 0,
        'promotional_sms': promotional_sms_count,
        'transactional_sms': transactional_sms_count,
        'reach': queryset.aggregate(total_reach=Sum('user_msgCount'))['total_reach'] or 0,
        'total_amount': queryset.aggregate(total_amount=Sum('user_msgCount'))['total_amount'] or 0,
    }
    
    # Prepare data for charts
    sms_type_data = {
        'labels': ['Promotional', 'Transactional'],
        'counts': [
            queryset.filter(msg_type='P').count(),
            queryset.filter(msg_type='T').count()
        ]
    }
    
    date_wise_sms = (
        queryset.annotate(date=TruncDate('created_at'))
        .values('date')
        .annotate(sms_count=Sum('user_msgCount'))
        .order_by('date')
    )
    queryset2 = MessageStatus.objects.filter(
        last_checked_at__date__range=[start_date, end_date],
        user=request.user
    )
    print(queryset2,"this is query set 2:")
    if start_date and end_date:
         filtered_sms = [entry for entry in date_wise_sms if start_date <= entry['date'] <= end_date]
    else:
        filtered_sms = date_wise_sms

# Prepare chart data
    date_labels = [entry['date'].strftime('%Y-%m-%d') for entry in filtered_sms]
    sms_counts = [entry['sms_count'] for entry in filtered_sms]
    delivered_count = queryset2.filter(status='SUCCESS', user=request.user).count()
    failed_count = queryset2.filter(status='FAILED', user=request.user).count()

        
  
    context = {
        'stats': stats,
        'sms_type_data': sms_type_data,
        'start_date': start_date,
        'end_date': end_date,
        'date_labels': date_labels,
        'sms_counts': sms_counts,
        'delivered_count': delivered_count,
        'failed_count': failed_count,
     
    }
    
    return render(request, 'sms_api_report.html', context)

@user_passes_test(admin_check, login_url='/login/')
def support_sendsmsapi(request):
    # Get filter inputs from the form
    start_date = request.POST.get('start_date')
    end_date = request.POST.get('end_date')
    phone = request.POST.get('phone')
    message_id = request.POST.get('messageid')
    username = request.POST.get('user') 

    data = SendSmsApiResponse.objects.all()
    filters_applied = False

    # Filter by date range (if provided)
    try:
        if start_date:
            filters_applied = True
            start_date_obj = datetime.strptime(start_date, '%Y-%m-%d').date()
            data = data.filter(created_at__date__gte=start_date_obj)
        if end_date:
            filters_applied = True
            end_date_obj = datetime.strptime(end_date, '%Y-%m-%d').date()
            data = data.filter(created_at__date__lte=end_date_obj)
    except ValueError:
        pass  # Ignore invalid dates silently

    # Filter by phone
    if phone:
         filters_applied = True
         data = data.filter(receiver__icontains=f'"{phone}"')

    # Filter by message ID
    if message_id:
        filters_applied = True
        data = data.filter(user_messageId__icontains=message_id)       

    # Filter by user (username string)
    if username:
        try:
            auth_user = CustomUser.objects.filter(username=username).first()
            data = data.filter(user=auth_user)
        except CustomUser.DoesNotExist:
            data = data.none() 
    
    if not filters_applied:
        data = data.order_by('created_at')[0:20]
    context = {
        'data': data,
        'start_date': start_date,
        'end_date': end_date,
        'phone': phone,
        'message_id': message_id,
        'user': username,
    }

    return render(request, "support_sendsmsapi.html", context)

@login_required
def webhook_list(request):
    """Display all webhooks for the current user"""
    if not check_user_permission(request.user, 'can_webhooks_configuration'):
           return redirect("access_denide")
    webhooks = Webhook.objects.filter(user=request.user, is_active=True)
    return render(request, 'webhooks_list.html', {'webhooks': webhooks})

@login_required
@require_http_methods(["GET", "POST"])
def webhook_create(request):
    """Create a new webhook"""
    if request.method == "POST":
        form = WebhookForm(request.POST)
        if form.is_valid():
            webhook = form.save(commit=False)
            webhook.user = request.user
            webhook.secret = secrets.token_hex(16)
            webhook.save()
            
            messages.success(request, "Webhook created successfully")
            return redirect('webhook_list')
    else:
        form = WebhookForm()
    
    return render(request, 'webhooks_create.html', {'form': form})

@login_required
@require_http_methods(["POST"])
def webhook_delete(request, webhook_id):
    """Delete (deactivate) a webhook"""
    try:
        webhook = Webhook.objects.get(id=webhook_id, user=request.user)
        webhook.is_active = False
        webhook.save()
        messages.success(request, "Webhook deleted successfully")
    except Webhook.DoesNotExist:
        messages.error(request, "Webhook not found")
    
    return redirect('webhook_list')

@login_required
@require_http_methods(["GET"])
def webhook_test(request, webhook_id):
    """Test a webhook by sending a test message"""
    try:
        webhook = Webhook.objects.get(id=webhook_id, user=request.user)
        
        return JsonResponse({
            "success": True,
            "message": "Test notification sent"
        })
    except Webhook.DoesNotExist:
        return JsonResponse({
            "success": False,
            "message": "Webhook not found"
        }, status=404)
        
        
@login_required
def generate_api_token(request):
    """View to generate or display API tokens"""
    if not check_user_permission(request.user, 'can_create_api_token'):
           return redirect("access_denide")
    api_credential = ApiCredentials.objects.filter(user=request.user).first()
    
    # Calculate token expiry
    token_expiry = None
    if api_credential and api_credential.token_updated_date:
        token_expiry = api_credential.token_updated_date + timedelta(hours=1)
        remaining_time = token_expiry - timezone.now()
        if remaining_time.total_seconds() > 0:
            # Format as minutes:seconds
            minutes, seconds = divmod(int(remaining_time.total_seconds()), 60)
            token_expiry_str = f"{minutes}m {seconds}s"
        else:
            token_expiry_str = "Expired"
    else:
        token_expiry_str = None
    
    context = {
        'api_credential': api_credential,
        'token_expiry': token_expiry_str
    }
    
    return render(request, 'api_token.html', context)

@login_required
@require_http_methods(["POST"])
def refresh_api_token(request):
    """View to generate or refresh API token"""
    try:
        # Get existing API credential or create a new one
        api_credential = ApiCredentials.objects.filter(user=request.user).first()
        
        # If we have an existing credential with a refresh token, try to refresh it
        if api_credential and api_credential.refresh_token:
            # Try to refresh using the refresh token
            refresh_headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_credential.refresh_token}"
            }
            
            try:
                refresh_response = requests.post(
                    "https://api.wtsdealnow.com/auth/token/refresh",
                    headers=refresh_headers,
                    timeout=10  # Add timeout
                )
                
                if refresh_response.status_code == 200:
                    # Update with new tokens
                    refresh_data = refresh_response.json()
                    token = refresh_data.get("token")
                    refresh_token = refresh_data.get("refresh_token")
                    
                    if token and refresh_token:
                        api_credential.token = token
                        api_credential.refresh_token = refresh_token
                        api_credential.token_updated_date = timezone.now()
                        api_credential.save()
                        messages.success(request, "API token refreshed successfully")
                        return redirect('generate_api_token')
                    else:
                        # If the response is missing tokens, fall back to generating a new token
                        messages.warning(request, "Refresh token response was incomplete, generating new token")
                else:
                    messages.warning(request, f"Failed to refresh token (HTTP {refresh_response.status_code}), trying to generate new token")
            except Exception as e:
                messages.warning(request, f"Error during token refresh: {str(e)}, trying to generate new token")
        
        # If we reach here, we need to generate a new token
        generate_new_token(request, api_credential)
            
    except Exception as e:
        messages.error(request, f"Error refreshing token: {str(e)}")
    
    return redirect('generate_api_token')

def generate_new_token(request, api_credential=None):
    """Helper function to generate a new token"""
    # Get username and password from form or user settings
    username = request.POST.get('username')
    password = request.POST.get('password')
    
    if not username or not password:
        messages.error(request, "Username and password are required")
        return
    
    # Request new token
    payload = {
        "username": username,
        "password": password
    }
    
    headers = {
        "Content-Type": "application/json"
    }
    
    try:
        response = requests.post(
            "https://api.wtsdealnow.com/auth/token",
            json=payload,
            headers=headers
        )
        
        if response.status_code == 200:
            token_data = response.json()
            
            # Validate that token and refresh_token exist in the response
            token = token_data.get("token")
            refresh_token = token_data.get("refresh_token")
            
            if not token or not refresh_token:
                messages.error(request, "API returned incomplete token data")
                return
                
            if api_credential:
                # Update existing credential
                api_credential.username = username
                api_credential.password = password
                api_credential.token = token
                api_credential.refresh_token = refresh_token
                api_credential.token_updated_date = timezone.now()
                api_credential.save()
            else:
                # Create new credential
                ApiCredentials.objects.create(
                    user=request.user,
                    username=username,
                    password=password,
                    token=token,
                    refresh_token=refresh_token,
                    token_updated_date=timezone.now()
                )
            
            messages.success(request, "New API token generated successfully")
        else:
            error_msg = f"Failed to generate token: {response.status_code}"
            try:
                error_detail = response.json()
                error_msg += f" - {error_detail}"
            except:
                error_msg += f" - {response.text}"
            
            messages.error(request, error_msg)
    except Exception as e:
        messages.error(request, f"Error generating token: {str(e)}")


@login_required
def access_denide(request):
    return render(request, "access_denide.html") 