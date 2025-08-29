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
]
