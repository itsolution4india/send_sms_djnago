from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import SenderID, CustomUser, Account, CoinHistory, CampaignDetails, ReportDetails
from .models import ApiCredentials, SendSmsApiResponse

class SenderIDAdmin(admin.ModelAdmin):
    list_display = ('username', 'sender_id', 'created_at')
    search_fields = ('username', 'sender_id')

class CustomUserAdmin(UserAdmin):
    list_display = ('username', 'email', 'phone_number', 'sender_id', 'is_staff')
    fieldsets = UserAdmin.fieldsets + (
        ('Extra Fields', {'fields': ('phone_number', 'sender_id', 'failed_login_attempts', 'last_failed_attempt', 'locked_until')}),
    )
    add_fieldsets = UserAdmin.add_fieldsets + (
        ('Extra Fields', {'fields': ('email', 'phone_number', 'sender_id')}),
    )
    search_fields = ('username', 'email', 'phone_number')

class AccountAdmin(admin.ModelAdmin):
    list_display = ('account_holder_name', 'account_number', 'account_id', 'gui_balance', 'api_balance', 'user')
    search_fields = ('account_holder_name', 'account_number', 'account_id')

class CoinHistoryAdmin(admin.ModelAdmin):
    list_display = ('transaction_id', 'user', 'transaction_type', 'category', 'coins', 'created_at')
    list_filter = ('transaction_type', 'category', 'user')
    search_fields = ('transaction_id', 'user__username', 'reason')
    readonly_fields = ('transaction_id', 'created_at')
    date_hierarchy = 'created_at'

admin.site.register(SenderID, SenderIDAdmin)
admin.site.register(CustomUser, CustomUserAdmin)
admin.site.register(Account, AccountAdmin)
admin.site.register(CoinHistory, CoinHistoryAdmin)
admin.site.register(CampaignDetails)
admin.site.register(ReportDetails)
admin.site.register(SendSmsApiResponse)
admin.site.register(ApiCredentials)