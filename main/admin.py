from django.contrib import admin
from .models import UserProfile, TwitterAccount, LeadList, Lead

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

@admin.register(LeadList)
class LeadListAdmin(admin.ModelAdmin):
    list_display = ['name', 'user', 'status', 'total_collected', 'max_leads', 'created_at']
    search_fields = ['name', 'user__username', 'user__email']
    list_filter = ['status', 'created_at', 'last_processed_at']
    readonly_fields = ['total_collected', 'created_at', 'updated_at', 'last_processed_at']
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'description', 'user')
        }),
        ('Target Sources', {
            'fields': ('target_usernames', 'target_post_urls'),
            'classes': ('collapse',)
        }),
        ('Filtering Criteria', {
            'fields': ('min_followers', 'max_followers', 'locations', 'bio_keywords', 'exclude_keywords'),
            'classes': ('collapse',)
        }),
        ('Collection Status', {
            'fields': ('status', 'total_collected', 'max_leads', 'error_message')
        }),
        ('Processing Info', {
            'fields': ('last_processed_at', 'current_batch_user', 'current_batch_offset'),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def delete_model(self, request, obj):
        """Custom delete method to ensure proper cleanup"""
        # Get the count of leads that will be deleted
        lead_count = obj.leads.count()
        
        # Delete the lead list (this will cascade delete all leads)
        obj.delete()
        
        # Log the deletion
        self.message_user(
            request, 
            f"Successfully deleted Lead List '{obj.name}' and {lead_count} associated leads.",
            level='SUCCESS'
        )
    
    def delete_queryset(self, request, queryset):
        """Custom delete method for bulk deletions"""
        total_leads = 0
        lead_list_names = []
        
        # Count total leads and collect names
        for lead_list in queryset:
            total_leads += lead_list.leads.count()
            lead_list_names.append(lead_list.name)
        
        # Delete the lead lists (this will cascade delete all leads)
        queryset.delete()
        
        # Log the bulk deletion
        self.message_user(
            request, 
            f"Successfully deleted {len(lead_list_names)} Lead Lists ({', '.join(lead_list_names)}) and {total_leads} associated leads.",
            level='SUCCESS'
        )

@admin.register(Lead)
class LeadAdmin(admin.ModelAdmin):
    list_display = ['username', 'display_name', 'lead_list', 'followers_count', 'location', 'source_type', 'verified', 'created_at']
    search_fields = ['username', 'display_name', 'lead_list__name', 'location', 'bio']
    list_filter = ['source_type', 'verified', 'created_at', 'lead_list__name']
    readonly_fields = ['created_at', 'updated_at']
    
    fieldsets = (
        ('Profile Information', {
            'fields': ('username', 'display_name', 'bio', 'location', 'verified')
        }),
        ('Statistics', {
            'fields': ('followers_count', 'following_count', 'tweet_count', 'profile_image_url')
        }),
        ('Lead List', {
            'fields': ('lead_list', 'source_type', 'source_reference')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
