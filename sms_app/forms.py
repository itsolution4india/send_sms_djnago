from django import forms
from .models import CoinHistory, SenderID, Webhook

class CoinHistoryForm(forms.ModelForm):
    class Meta:
        model = CoinHistory
        fields = ['user', 'coins', 'category', 'transaction_type']

class SenderIDSelectForm(forms.Form):
    sender_id = forms.ModelChoiceField(queryset=SenderID.objects.all(), widget=forms.Select(attrs={'class': 'form-control'}))

class WebhookForm(forms.ModelForm):
    class Meta:
        model = Webhook
        fields = ['url']
        widgets = {
            'url': forms.URLInput(attrs={'class': 'form-control', 'placeholder': 'https://example.com/webhook'})
        }
    
    def clean_url(self):
        url = self.cleaned_data['url']
        if not url.startswith(('http://', 'https://')):
            raise forms.ValidationError("URL must start with http:// or https://")
        return url