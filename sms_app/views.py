from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib import messages
from django.utils import timezone
from datetime import timedelta
from django.contrib.auth.decorators import login_required
from .models import CustomUser, CoinHistory, Account, CampaignDetails, ReportDetails, SendSmsApiResponse
from .forms import CoinHistoryForm
import csv
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
from .utils import logger

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


@login_required
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

    return render(request, 'billing.html', {'transactions': transactions, 'account': account, "user": user})


class SendSMSView(LoginRequiredMixin, View):
    login_url = '/login/'
    redirect_field_name = 'redirect_to'
    
    def get(self, request):
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
    reports = ReportDetails.objects.all()

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
    return render(request, 'api_documentation.html')

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
    
    context = {
        'stats': stats,
        'sms_type_data': sms_type_data,
        'start_date': start_date,
        'end_date': end_date,
    }
    
    return render(request, 'sms_api_report.html', context)