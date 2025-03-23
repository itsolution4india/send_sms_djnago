from django import forms
from .models import CoinHistory, SenderID

class CoinHistoryForm(forms.ModelForm):
    class Meta:
        model = CoinHistory
        fields = ['user', 'coins', 'category', 'transaction_type']

class SenderIDSelectForm(forms.Form):
    sender_id = forms.ModelChoiceField(queryset=SenderID.objects.all(), widget=forms.Select(attrs={'class': 'form-control'}))
