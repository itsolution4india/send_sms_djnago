from django.urls import path
from . import views

urlpatterns = [
    path('admin_view/', views.admin_view, name='admin_view'),
    path('', views.login_view, name='login'),
    path('dashboard/', views.dashboard_view, name='dashboard'),
    path('billing/', views.billing_view, name='billing'),
    path('send-sms/', views.send_sms, name='send_sms'),
    path('logout/', views.logout_view, name='logout'),
    path('send-sms/', views.send_sms, name='send_sms'),
    path('sms-logs/', views.sms_logs, name='sms_logs'),
]