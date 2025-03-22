from django import forms
from .models import CoinHistory, SenderID, SMSLog
import csv
import io
import json
import requests
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .forms import SMSForm
import threading

class CoinHistoryForm(forms.ModelForm):
    class Meta:
        model = CoinHistory
        fields = ['user', 'coins', 'category', 'transaction_type']

class SenderIDSelectForm(forms.Form):
    sender_id = forms.ModelChoiceField(queryset=SenderID.objects.all(), widget=forms.Select(attrs={'class': 'form-control'}))


class SMSForm(forms.ModelForm):
    MSG_TYPES = [
        ('T', 'Transactional'),
        ('P', 'Promotional'),
    ]
    REQUEST_TYPES = [
        ('S', 'Single'),
        ('B', 'Bulk'),
    ]
    
    msg_type = forms.ChoiceField(choices=MSG_TYPES, widget=forms.RadioSelect)
    request_type = forms.ChoiceField(choices=REQUEST_TYPES, widget=forms.RadioSelect)
    receiver = forms.CharField(required=False, widget=forms.Textarea(attrs={'placeholder': 'Enter phone numbers separated by commas for single message'}))
    receiver_file = forms.FileField(required=False, help_text='Upload CSV file with Phone_numbers column')
    content = forms.CharField(widget=forms.Textarea(attrs={'placeholder': 'Enter message content here'}))
    
    class Meta:
        model = SMSLog
        fields = ['msg_type', 'request_type', 'content']
    
    def clean(self):
        cleaned_data = super().clean()
        request_type = cleaned_data.get('request_type')
        receiver = cleaned_data.get('receiver')
        receiver_file = cleaned_data.get('receiver_file')
        msg_type = cleaned_data.get('msg_type')
        
        # Content type logic
        if msg_type == 'P':
            cleaned_data['content_type'] = 2  # Unicode for promotional
        else:
            cleaned_data['content_type'] = 1  # Regular for transactional
        
        # Validate receiver inputs
        if request_type == 'S' and not receiver:
            raise forms.ValidationError("You must provide at least one receiver phone number for single messages")
        
        if request_type == 'B' and not receiver_file:
            raise forms.ValidationError("You must upload a CSV file for bulk messages")
        
        # Process receiver file if provided
        if receiver_file:
            try:
                decoded_file = receiver_file.read().decode('utf-8')
                io_string = io.StringIO(decoded_file)
                csv_reader = csv.DictReader(io_string)
                phone_numbers = []
                
                for row in csv_reader:
                    if 'Phone_numbers' in row:
                        phone_number = row['Phone_numbers'].strip()
                        if phone_number:
                            phone_numbers.append(phone_number)
                
                if not phone_numbers:
                    raise forms.ValidationError("No valid phone numbers found in the CSV file")
                
                cleaned_data['receiver_numbers'] = phone_numbers
            except Exception as e:
                raise forms.ValidationError(f"Error processing CSV file: {str(e)}")
        elif receiver:
            # Process comma-separated phone numbers
            phone_numbers = [num.strip() for num in receiver.split(',') if num.strip()]
            cleaned_data['receiver_numbers'] = phone_numbers
        
        return cleaned_data
    
@login_required
def send_sms(request):
    if request.method == 'POST':
        form = SMSForm(request.POST, request.FILES)
        if form.is_valid():
            # Get sender_id from the logged-in user
            user = request.user
            if not user.sender_id:
                messages.error(request, "You don't have a sender ID configured. Please contact admin.")
                return redirect('send_sms')
            
            sender_id_obj = user.sender_id
            
            # Create SMS Log
            sms_log = SMSLog(
                user=user,
                sender=sender_id_obj.sender_id,
                receiver=json.dumps(form.cleaned_data['receiver_numbers']),
                content=form.cleaned_data['content'],
                msg_type=form.cleaned_data['msg_type'],
                request_type=form.cleaned_data['request_type'],
                content_type=form.cleaned_data['content_type'],
                status='PENDING'
            )
            sms_log.save()
            
            # Send SMS in background thread
            thread = threading.Thread(
                target=process_sms_sending,
                args=(sms_log.id, sender_id_obj.token, sender_id_obj.sender_id)
            )
            thread.start()
            
            messages.success(request, "SMS sending has been initiated. Check status in SMS logs.")
            return redirect('sms_logs')
    else:
        form = SMSForm()
    
    return render(request, 'sms_app/send_sms.html', {'form': form})

def process_sms_sending(sms_log_id, token, sender_id):
    try:
        sms_log = SMSLog.objects.get(id=sms_log_id)
        receiver_numbers = json.loads(sms_log.receiver)
        
        # API endpoint
        url = 'https://api.mobireach.com.bd/sms/send'
        
        # Headers
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {token}'
        }
        
        # Prepare payload
        payload = {
            'sender': sender_id,
            'receiver': receiver_numbers,
            'content': sms_log.content,
            'msgType': sms_log.msg_type,
            'requestType': sms_log.request_type,
            'contentType': sms_log.content_type
        }
        
        # Send the request
        response = requests.post(url, headers=headers, json=payload)
        
        # Update the SMS log
        sms_log.response_data = response.text
        if response.status_code == 200:
            sms_log.status = 'SENT'
        else:
            sms_log.status = 'FAILED'
        
        sms_log.save()
    except Exception as e:
        # Log the error
        try:
            sms_log = SMSLog.objects.get(id=sms_log_id)
            sms_log.status = 'FAILED'
            sms_log.response_data = str(e)
            sms_log.save()
        except:
            pass

@login_required
def sms_logs(request):
    logs = SMSLog.objects.filter(user=request.user).order_by('-created_at')
    return render(request, 'sms_app/sms_logs.html', {'logs': logs})