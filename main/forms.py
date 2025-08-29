from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from .models import TwitterAccount
import json

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
