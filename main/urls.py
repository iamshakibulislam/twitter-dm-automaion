from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('login/', views.login_view, name='login'),
    path('signup/', views.signup_view, name='signup'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('dashboard/index/', views.dashboard, name='dashboard_index'),
    path('logout/', views.logout_view, name='logout'),
    
    # Account management URLs
    path('accounts/', views.accounts_list, name='accounts_list'),
    path('accounts/add/', views.accounts_add, name='accounts_add'),
    path('accounts/<int:account_id>/test/', views.accounts_test, name='accounts_test'),
    path('accounts/<int:account_id>/delete/', views.accounts_delete, name='accounts_delete'),
    
    # Lead Builder URLs
    path('lead-builder/', views.lead_builder_list, name='lead_builder_list'),
    path('lead-builder/create/', views.lead_builder_create, name='lead_builder_create'),
    path('lead-builder/<int:lead_list_id>/', views.lead_builder_detail, name='lead_builder_detail'),
    path('lead-builder/<int:lead_list_id>/edit/', views.lead_builder_edit, name='lead_builder_edit'),
    path('lead-builder/<int:lead_list_id>/delete/', views.lead_builder_delete, name='lead_builder_delete'),
    path('lead-builder/<int:lead_list_id>/pause/', views.lead_builder_pause, name='lead_builder_pause'),
    path('lead-builder/<int:lead_list_id>/export/', views.lead_export, name='lead_export'),
]
