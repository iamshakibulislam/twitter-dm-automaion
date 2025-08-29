from django.contrib import admin
from .models import UserProfile, TwitterAccount

@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ['user', 'twitter_handle', 'created_at']
    search_fields = ['user__username', 'user__email', 'twitter_handle']
    list_filter = ['created_at']

@admin.register(TwitterAccount)
class TwitterAccountAdmin(admin.ModelAdmin):
    list_display = ['user', 'username', 'display_name', 'is_verified', 'is_active', 'created_at']
    search_fields = ['user__username', 'user__email', 'username', 'display_name']
    list_filter = ['is_verified', 'is_active', 'created_at', 'last_verified']
    readonly_fields = ['created_at', 'updated_at']
    
    fieldsets = (
        ('Account Info', {
            'fields': ('user', 'username', 'display_name')
        }),
        ('Authentication', {
            'fields': ('auth_token', 'ct0_token'),
            'classes': ('collapse',)
        }),
        ('Status', {
            'fields': ('is_active', 'is_verified', 'last_verified')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
