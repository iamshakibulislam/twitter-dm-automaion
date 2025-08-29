from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from .models import TwitterAccount, LeadList
import json
import re

class SignUpForm(UserCreationForm):
    """Custom signup form with email and first name"""
    first_name = forms.CharField(
        max_length=30,
        required=True,
        widget=forms.TextInput(attrs={
            'class': 'mt-1 block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500',
            'placeholder': 'Enter your first name'
        })
    )
    
    email = forms.EmailField(
        max_length=254,
        required=True,
        widget=forms.EmailInput(attrs={
            'class': 'mt-1 block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500',
            'placeholder': 'Enter your email'
        })
    )
    
    password1 = forms.CharField(
        label='Password',
        widget=forms.PasswordInput(attrs={
            'class': 'mt-1 block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500',
            'placeholder': 'Create a password'
        })
    )
    
    password2 = forms.CharField(
        label='Confirm Password',
        widget=forms.PasswordInput(attrs={
            'class': 'mt-1 block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500',
            'placeholder': 'Confirm your password'
        })
    )
    
    class Meta:
        model = User
        fields = ('first_name', 'email', 'password1', 'password2')
    
    def clean_email(self):
        email = self.cleaned_data.get('email')
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError('This email is already registered.')
        return email
    
    def clean(self):
        cleaned_data = super().clean()
        password1 = cleaned_data.get('password1')
        password2 = cleaned_data.get('password2')
        
        if password1 and password2 and password1 != password2:
            raise forms.ValidationError('Passwords do not match.')
        
        return cleaned_data

class TwitterAccountForm(forms.ModelForm):
    """Form for adding Twitter account via cookies"""
    cookies_data = forms.CharField(
        widget=forms.Textarea(attrs={
            'class': 'mt-1 block w-full px-4 py-3 border border-gray-300 rounded-xl shadow-sm focus:outline-none focus:ring-purple-500 focus:border-purple-500 bg-neutral-800/50 text-white placeholder-gray-400',
            'placeholder': 'Paste your Twitter cookies JSON here...\n[\n  {\n    "name": "auth_token",\n    "value": "your_auth_token_here"\n  },\n  {\n    "name": "ct0",\n    "value": "your_ct0_token_here"\n  }\n]',
            'rows': 12
        }),
        help_text='Paste the JSON array of cookies exported from your browser'
    )
    
    class Meta:
        model = TwitterAccount
        fields = []
    
    def clean_cookies_data(self):
        cookies_data = self.cleaned_data.get('cookies_data')
        if not cookies_data:
            raise forms.ValidationError('Please provide cookies data.')
        
        try:
            cookies = json.loads(cookies_data)
        except json.JSONDecodeError:
            raise forms.ValidationError('Invalid JSON format. Please check your cookies data.')
        
        if not isinstance(cookies, list):
            raise forms.ValidationError('Cookies data should be a JSON array.')
        
        # Extract required cookies
        auth_token = None
        ct0_token = None
        
        for cookie in cookies:
            if not isinstance(cookie, dict):
                continue
            
            cookie_name = cookie.get('name', '')
            cookie_value = cookie.get('value', '')
            
            if cookie_name == 'auth_token':
                auth_token = cookie_value
            elif cookie_name == 'ct0':
                ct0_token = cookie_value
        
        if not auth_token:
            raise forms.ValidationError('auth_token cookie not found in the provided data.')
        
        if not ct0_token:
            raise forms.ValidationError('ct0 cookie not found in the provided data.')
        
        # Debug: Print extracted values
        print(f"DEBUG: Extracted auth_token: {auth_token[:20] if auth_token else 'None'}...")
        print(f"DEBUG: Extracted ct0: {ct0_token[:20] if ct0_token else 'None'}...")
        
        return {
            'auth_token': auth_token,
            'ct0': ct0_token,
            'raw_cookies': cookies
        }
    
    def save(self, user, commit=True):
        """Save the Twitter account with extracted cookie data"""
        cookies_info = self.cleaned_data['cookies_data']
        
        twitter_account = TwitterAccount(
            user=user,
            auth_token=cookies_info['auth_token'],
            ct0_token=cookies_info['ct0'],
            is_verified=False
        )
        
        if commit:
            twitter_account.save()
        
        return twitter_account

class LeadListForm(forms.ModelForm):
    """Form for creating and editing lead lists"""
    
    # Target configuration
    target_usernames_text = forms.CharField(
        required=False,
        widget=forms.HiddenInput(attrs={
            'id': 'target_usernames_hidden'
        }),
        help_text='Twitter usernames or profile URLs to target their followers'
    )
    
    target_post_urls_text = forms.CharField(
        required=False,
        widget=forms.HiddenInput(attrs={
            'id': 'target_post_urls_hidden'
        }),
        help_text='Twitter post URLs to target users who commented on these posts'
    )
    
    # Filtering criteria
    locations_text = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'mt-1 block w-full px-4 py-3 border border-gray-300 rounded-xl shadow-sm focus:outline-none focus:ring-purple-500 focus:border-purple-500 bg-neutral-800/50 text-white placeholder-gray-400',
            'placeholder': 'Enter locations to filter by (one per line)\nExample:\nNew York\nLondon\nTokyo',
            'rows': 4
        }),
        help_text='Filter users by location (leave empty to include all locations)'
    )
    
    bio_keywords_text = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'mt-1 block w-full px-4 py-3 border border-gray-300 rounded-xl shadow-sm focus:outline-none focus:ring-purple-500 focus:border-purple-500 bg-neutral-800/50 text-white placeholder-gray-400',
            'placeholder': 'Enter keywords to match in bio (one per line)\nExample:\nentrepreneur\nfounder\nCEO',
            'rows': 4
        }),
        help_text='Include users whose bio contains any of these keywords'
    )
    
    exclude_keywords_text = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'mt-1 block w-full px-4 py-3 border border-gray-300 rounded-xl shadow-sm focus:outline-none focus:ring-purple-500 focus:border-purple-500 bg-neutral-800/50 text-white placeholder-gray-400',
            'placeholder': 'Enter keywords to exclude from bio (one per line)\nExample:\nbot\nspam\nfake',
            'rows': 4
        }),
        help_text='Exclude users whose bio contains any of these keywords'
    )
    
    class Meta:
        model = LeadList
        fields = ['name', 'description', 'min_followers', 'max_followers', 'max_leads']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'mt-1 block w-full px-4 py-3 border border-gray-300 rounded-xl shadow-sm focus:outline-none focus:ring-purple-500 focus:border-purple-500 bg-neutral-800/50 text-white placeholder-gray-400',
                'placeholder': 'Enter a name for your lead list'
            }),
            'description': forms.Textarea(attrs={
                'class': 'mt-1 block w-full px-4 py-3 border border-gray-300 rounded-xl shadow-sm focus:outline-none focus:ring-purple-500 focus:border-purple-500 bg-neutral-800/50 text-white placeholder-gray-400',
                'placeholder': 'Describe this lead list (optional)',
                'rows': 3
            }),

            'min_followers': forms.NumberInput(attrs={
                'class': 'mt-1 block w-full px-4 py-3 border border-gray-300 rounded-xl shadow-sm focus:outline-none focus:ring-purple-500 focus:border-purple-500 bg-neutral-800/50 text-white',
                'min': 0,
                'placeholder': '0'
            }),
            'max_followers': forms.NumberInput(attrs={
                'class': 'mt-1 block w-full px-4 py-3 border border-gray-300 rounded-xl shadow-sm focus:outline-none focus:ring-purple-500 focus:border-purple-500 bg-neutral-800/50 text-white',
                'min': 1,
                'placeholder': '1000000'
            }),
            'max_leads': forms.NumberInput(attrs={
                'class': 'mt-1 block w-full px-4 py-3 border border-gray-300 rounded-xl shadow-sm focus:outline-none focus:ring-purple-500 focus:border-purple-500 bg-neutral-800/50 text-white',
                'min': 1,
                'max': 1000000,
                'placeholder': '1000'
            })
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            # Populate text fields from JSON data
            self.fields['target_usernames_text'].initial = '\n'.join(self.instance.target_usernames)
            self.fields['target_post_urls_text'].initial = '\n'.join(self.instance.target_post_urls)
            self.fields['locations_text'].initial = '\n'.join(self.instance.locations)
            self.fields['bio_keywords_text'].initial = '\n'.join(self.instance.bio_keywords)
            self.fields['exclude_keywords_text'].initial = '\n'.join(self.instance.exclude_keywords)
    
    def clean_target_usernames_text(self):
        """Clean and validate usernames and profile URLs"""
        text = self.cleaned_data.get('target_usernames_text', '').strip()
        if not text:
            return []
        
        usernames = []
        for line in text.split('\n'):
            item = line.strip()
            if item:
                # Check if it's a profile URL
                if item.startswith(('https://twitter.com/', 'https://x.com/')):
                    # Extract username from profile URL
                    match = re.search(r'https?://(twitter\.com|x\.com)/([A-Za-z0-9_]{1,15})', item)
                    if match:
                        username = match.group(2)
                        usernames.append(username)
                    else:
                        raise forms.ValidationError(f'Invalid Twitter profile URL: {item}')
                else:
                    # Treat as username
                    username = item.lstrip('@')
                    # Basic validation
                    if not re.match(r'^[A-Za-z0-9_]{1,15}$', username):
                        raise forms.ValidationError(f'Invalid username format: {username}')
                    usernames.append(username)
        
        return usernames
    
    def clean_target_post_urls_text(self):
        """Clean and validate post URLs"""
        text = self.cleaned_data.get('target_post_urls_text', '').strip()
        if not text:
            return []
        
        urls = []
        for line in text.split('\n'):
            url = line.strip()
            if url:
                # Validate Twitter URL format
                if not re.match(r'^https?://(twitter\.com|x\.com)/.+/status/\d+', url):
                    raise forms.ValidationError(f'Invalid Twitter post URL: {url}')
                urls.append(url)
        
        return urls
    
    def clean_locations_text(self):
        """Clean locations list"""
        text = self.cleaned_data.get('locations_text', '').strip()
        if not text:
            return []
        
        return [line.strip() for line in text.split('\n') if line.strip()]
    
    def clean_bio_keywords_text(self):
        """Clean bio keywords list"""
        text = self.cleaned_data.get('bio_keywords_text', '').strip()
        if not text:
            return []
        
        return [line.strip().lower() for line in text.split('\n') if line.strip()]
    
    def clean_exclude_keywords_text(self):
        """Clean exclude keywords list"""
        text = self.cleaned_data.get('exclude_keywords_text', '').strip()
        if not text:
            return []
        
        return [line.strip().lower() for line in text.split('\n') if line.strip()]
    
    def clean(self):
        """Validate the form data"""
        cleaned_data = super().clean()
        
        target_usernames = cleaned_data.get('target_usernames_text', [])
        target_post_urls = cleaned_data.get('target_post_urls_text', [])
        
        # At least one source must be specified
        if not target_usernames and not target_post_urls:
            raise forms.ValidationError('You must specify at least one Twitter username or post URL to target.')
        
        # Validate follower range
        min_followers = cleaned_data.get('min_followers', 0)
        max_followers = cleaned_data.get('max_followers', 1000000)
        
        if min_followers >= max_followers:
            raise forms.ValidationError('Minimum followers must be less than maximum followers.')
        
        return cleaned_data
    
    def save(self, user, commit=True):
        """Save the lead list with processed data"""
        lead_list = super().save(commit=False)
        lead_list.user = user
        
        # Convert text inputs to JSON lists using the cleaned data
        lead_list.target_usernames = self.cleaned_data.get('target_usernames_text', [])
        lead_list.target_post_urls = self.cleaned_data.get('target_post_urls_text', [])
        lead_list.locations = self.cleaned_data.get('locations_text', [])
        lead_list.bio_keywords = self.cleaned_data.get('bio_keywords_text', [])
        lead_list.exclude_keywords = self.cleaned_data.get('exclude_keywords_text', [])
        
        if commit:
            lead_list.save()
        
        return lead_list

class LoginForm(forms.Form):
    """Custom login form with email and password"""
    email = forms.EmailField(
        widget=forms.EmailInput(attrs={
            'class': 'mt-1 block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500',
            'placeholder': 'Enter your email'
        })
    )
    
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'mt-1 block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500',
            'placeholder': 'Enter your password'
        })
    )
