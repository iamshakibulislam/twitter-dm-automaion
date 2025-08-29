from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save
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

@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    """Create user profile when user is created"""
    if created:
        UserProfile.objects.create(user=instance)

@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    """Save user profile when user is saved"""
    instance.profile.save()
