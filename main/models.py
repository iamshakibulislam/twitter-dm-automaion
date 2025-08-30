from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save, pre_delete
from django.dispatch import receiver
import json

class UserProfile(models.Model):
    """Extended user profile for additional information"""
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    twitter_handle = models.CharField(max_length=100, blank=True, null=True)
    bio = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"{self.user.first_name}'s Profile"

class TwitterAccount(models.Model):
    """Twitter account managed by a user"""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='twitter_accounts')
    username = models.CharField(max_length=100, blank=True, null=True)
    display_name = models.CharField(max_length=100, blank=True, null=True)
    auth_token = models.TextField()  # Store the auth_token cookie
    ct0_token = models.TextField()   # Store the ct0 cookie
    is_active = models.BooleanField(default=True)
    is_verified = models.BooleanField(default=False)
    last_verified = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ['user', 'username']
    
    def __str__(self):
        return f"@{self.username}" if self.username else f"Twitter Account {self.id}"
    
    def get_cookies_dict(self):
        """Return cookies in format expected by twikit"""
        return {
            'auth_token': self.auth_token,
            'ct0': self.ct0_token
        }

class LeadList(models.Model):
    """Lead list configuration and metadata"""
    STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('COLLECTING', 'Collecting'),
        ('COMPLETED', 'Completed'),
        ('PAUSED', 'Paused'),
        ('ERROR', 'Error'),
    ]
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='lead_lists')
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True, null=True)
    
    # Source configuration
    target_usernames = models.JSONField(default=list, help_text="List of Twitter usernames to target followers")
    target_post_urls = models.JSONField(default=list, help_text="List of Twitter post URLs to target commenters")
    
    # Filtering criteria
    min_followers = models.IntegerField(default=0)
    max_followers = models.IntegerField(default=1000000)
    locations = models.JSONField(default=list, blank=True, help_text="List of target locations")
    bio_keywords = models.JSONField(default=list, blank=True, help_text="Keywords to match in bio")
    exclude_keywords = models.JSONField(default=list, blank=True, help_text="Keywords to exclude from bio")
    
    # Collection status
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='PENDING')
    total_collected = models.IntegerField(default=0)
    max_leads = models.IntegerField(default=1000000)  # Hard limit of 1M
    estimated_total_leads = models.IntegerField(default=0, help_text="Estimated total leads available based on followers found")
    
    # Processing tracking
    last_processed_at = models.DateTimeField(blank=True, null=True)
    current_batch_user = models.CharField(max_length=100, blank=True, null=True)
    current_batch_offset = models.IntegerField(default=0)
    error_message = models.TextField(blank=True, null=True)
    
    # Advanced pagination state (JSON field to store pagination cursors/tokens)
    pagination_state = models.JSONField(
        default=dict,
        help_text="Stores pagination state for each target (usernames, post URLs)"
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"{self.name} ({self.total_collected} leads)"
    
    def can_collect_more(self):
        """Check if more leads can be collected"""
        return self.total_collected < self.max_leads and self.status in ['PENDING', 'COLLECTING']
    
    def reset_pagination_state(self):
        """Reset pagination state to start fresh collection"""
        self.pagination_state = {}
        self.current_batch_user = None
        self.current_batch_offset = 0
        self.save(update_fields=['pagination_state', 'current_batch_user', 'current_batch_offset'])
    
    def get_pagination_progress(self):
        """Get collection progress for each target"""
        if not self.pagination_state:
            return {}
        
        progress = {}
        for key, state in self.pagination_state.items():
            # Handle both old format (followers_username) and new format (username)
            if key.startswith('followers_'):
                username = key.replace('followers_', '')
            else:
                username = key
                
            progress[f"@{username}"] = {
                'type': 'followers',
                'collected': state.get('collected', 0),
                'completed': not state.get('has_more', True),
                'last_processed': state.get('last_updated', 'Never')
            }
        
        return progress
    
    def get_progress_percentage(self):
        """Calculate progress percentage based on estimated total leads"""
        if self.estimated_total_leads == 0:
            return 0
        return min(100, int((self.total_collected / self.estimated_total_leads) * 100))
    
    def get_progress_display(self):
        """Get formatted progress display"""
        if self.estimated_total_leads == 0:
            return f"{self.total_collected} leads collected"
        percentage = self.get_progress_percentage()
        return f"{percentage}% complete ({self.total_collected}/{self.estimated_total_leads})"
    
    def get_total_sources_count(self):
        """Get total number of target sources"""
        return len(self.target_usernames or []) + len(self.target_post_urls or [])
    
    def update_estimated_total(self, new_estimate):
        """Update estimated total leads (only increase, never decrease)"""
        if new_estimate > self.estimated_total_leads:
            self.estimated_total_leads = new_estimate
            self.save(update_fields=['estimated_total_leads'])
    
    def delete(self, *args, **kwargs):
        """Custom delete method to ensure proper cleanup of leads"""
        # Get the count of leads that will be deleted
        lead_count = self.leads.count()
        
        # Call the parent delete method (this will cascade delete all leads)
        result = super().delete(*args, **kwargs)
        
        # Log the deletion if possible
        try:
            from django.contrib import messages
            messages.success(None, f"Deleted Lead List '{self.name}' and {lead_count} associated leads.")
        except:
            pass  # If messages framework is not available, just continue
        
        return result

class Lead(models.Model):
    """Individual lead profile"""
    lead_list = models.ForeignKey(LeadList, on_delete=models.CASCADE, related_name='leads')
    
    # Twitter profile data
    username = models.CharField(max_length=100)
    display_name = models.CharField(max_length=200, blank=True, null=True)
    bio = models.TextField(blank=True, null=True)
    location = models.CharField(max_length=200, blank=True, null=True)
    followers_count = models.IntegerField(default=0)
    following_count = models.IntegerField(default=0)
    tweet_count = models.IntegerField(default=0)
    profile_image_url = models.URLField(blank=True, null=True)
    verified = models.BooleanField(default=False)
    
    # Collection metadata
    source_type = models.CharField(max_length=20, choices=[
        ('FOLLOWER', 'Follower'),
        ('COMMENTER', 'Commenter'),
    ])
    source_reference = models.CharField(max_length=200)  # Username or post URL
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ['lead_list', 'username']
        indexes = [
            models.Index(fields=['lead_list', 'username'], name='lead_list_username_idx'),
            models.Index(fields=['lead_list', 'created_at'], name='lead_list_created_idx'),
        ]
    
    def __str__(self):
        return f"@{self.username} ({self.display_name})"

@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    """Create user profile when user is created"""
    if created:
        UserProfile.objects.create(user=instance)

@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    """Save user profile when user is saved"""
    instance.profile.save()

@receiver(pre_delete, sender=LeadList)
def log_lead_list_deletion(sender, instance, **kwargs):
    """Log when a LeadList is being deleted"""
    lead_count = instance.leads.count()
    print(f"🗑️  Deleting Lead List '{instance.name}' with {lead_count} associated leads")
