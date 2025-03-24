from django.urls import path
from . import views

urlpatterns = [
    path('admin_view/', views.admin_view, name='admin_view'),
    path('', views.login_view, name='login'),
    path('dashboard/', views.dashboard_view, name='dashboard'),
    path('billing/', views.billing_view, name='billing'),
    path('logout/', views.logout_view, name='logout'),
    path('start-campaign/', views.SendSMSView.as_view(), name='send_sms'),
    path('reports/', views.report_view, name='report_view'),
    path('reports/delete/', views.delete_report, name='delete_report'),
    path('reports/fetch_latest/', views.fetch_latest_report, name='fetch_latest'),
    path('profile/', views.profile_view, name='profile'),
]