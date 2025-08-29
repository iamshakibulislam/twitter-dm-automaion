from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, JsonResponse
from .forms import SignUpForm, LoginForm, TwitterAccountForm
from .models import TwitterAccount
import asyncio
import json
from django.utils import timezone

def home(request):
    """Home page view"""
    return render(request, 'home.html')

def login_view(request):
    """Login view"""
    if request.user.is_authenticated:
        return redirect('dashboard')
    
    if request.method == 'POST':
        form = LoginForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data['email']
            password = form.cleaned_data['password']
            
            try:
                user = User.objects.get(email=email)
                user = authenticate(request, username=user.username, password=password)
                if user is not None:
                    login(request, user)
                    messages.success(request, f'Welcome back, {user.first_name}!')
                    return redirect('dashboard')
                else:
                    messages.error(request, 'Invalid email or password.')
            except User.DoesNotExist:
                messages.error(request, 'Invalid email or password.')
    else:
        form = LoginForm()
    
    return render(request, 'login.html', {'form': form})

def signup_view(request):
    """Signup view"""
    if request.user.is_authenticated:
        return redirect('dashboard')
    
    if request.method == 'POST':
        form = SignUpForm(request.POST)
        if form.is_valid():
            try:
                # Generate username from email
                email = form.cleaned_data['email']
                username = email.split('@')[0]
                base_username = username
                counter = 1
                
                # Ensure unique username
                while User.objects.filter(username=username).exists():
                    username = f"{base_username}{counter}"
                    counter += 1
                
                user = form.save(commit=False)
                user.username = username
                user.save()
                
                # Auto login after signup
                login(request, user)
                messages.success(request, f'Welcome to XOutreacher, {user.first_name}!')
                return redirect('dashboard')
                
            except Exception as e:
                messages.error(request, 'An error occurred during signup. Please try again.')
    else:
        form = SignUpForm()
    
    return render(request, 'signup.html', {'form': form})

@login_required
def dashboard(request):
    """Dashboard view - requires login"""
    return render(request, 'dashboard/index.html')

def logout_view(request):
    """Logout view"""
    logout(request)
    messages.success(request, 'You have been logged out successfully.')
    return redirect('home')

@login_required
def accounts_list(request):
    """List all Twitter accounts for the current user"""
    accounts = TwitterAccount.objects.filter(user=request.user).order_by('-created_at')
    return render(request, 'dashboard/accounts/list.html', {'accounts': accounts})

@login_required
def accounts_add(request):
    """Add a new Twitter account via cookies"""
    if request.method == 'POST':
        form = TwitterAccountForm(request.POST)
        if form.is_valid():
            print("DEBUG: Form is valid, saving Twitter account...")
            twitter_account = form.save(user=request.user)
            print(f"DEBUG: Saved account with ID: {twitter_account.id}")
            print(f"DEBUG: Saved auth_token: {twitter_account.auth_token[:20]}...")
            print(f"DEBUG: Saved ct0_token: {twitter_account.ct0_token[:20]}...")
            
            messages.success(request, 'Twitter account cookies have been saved. Testing connection...')
            
            # Test connection in the background
            try:
                print("DEBUG: Starting connection test...")
                test_result = test_twitter_connection(twitter_account)
                print(f"DEBUG: Test result: {test_result}")
                
                if test_result['success']:
                    twitter_account.is_verified = True
                    twitter_account.username = test_result.get('username', '')
                    twitter_account.display_name = test_result.get('display_name', '')
                    twitter_account.last_verified = timezone.now()
                    twitter_account.save()
                    username_display = twitter_account.username if twitter_account.username else 'Connected Account'
                    messages.success(request, f'✅ Twitter account {username_display} connected successfully!')
                else:
                    twitter_account.is_verified = False
                    twitter_account.save()
                    messages.error(request, f'❌ Failed to connect Twitter account: {test_result.get("error", "Unknown error")}')
            except Exception as e:
                print(f"DEBUG: Exception during connection test: {str(e)}")
                messages.error(request, f'❌ Error testing connection: {str(e)}')
            
            return redirect('accounts_list')
    else:
        form = TwitterAccountForm()
    
    return render(request, 'dashboard/accounts/add.html', {'form': form})

@login_required
def accounts_test(request, account_id):
    """Test connection for a specific Twitter account"""
    account = get_object_or_404(TwitterAccount, id=account_id, user=request.user)
    
    try:
        test_result = test_twitter_connection(account)
        if test_result['success']:
            account.is_verified = True
            account.username = test_result.get('username', account.username)
            account.display_name = test_result.get('display_name', account.display_name)
            account.last_verified = timezone.now()
            account.save()
            
            return JsonResponse({
                'success': True,
                'message': f'✅ Connection successful! @{account.username}',
                'username': account.username,
                'display_name': account.display_name
            })
        else:
            account.is_verified = False
            account.save()
            return JsonResponse({
                'success': False,
                'message': f'❌ Connection failed: {test_result.get("error", "Unknown error")}'
            })
    
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': f'❌ Error testing connection: {str(e)}'
        })

@login_required
def accounts_delete(request, account_id):
    """Delete a Twitter account"""
    account = get_object_or_404(TwitterAccount, id=account_id, user=request.user)
    
    if request.method == 'POST':
        username = account.username or f'Account {account.id}'
        account.delete()
        messages.success(request, f'Twitter account {username} has been removed.')
        return redirect('accounts_list')
    
    return render(request, 'dashboard/accounts/delete.html', {'account': account})

def test_twitter_connection(twitter_account):
    """Test Twitter account connection using twikit"""
    try:
        # Import twikit here to avoid issues if not installed
        from twikit import Client
        
        # Get cookies in the format expected by twikit (exactly like your working example)
        cookies = twitter_account.get_cookies_dict()
        
        # Debug: Print what we're about to test
        print(f"DEBUG: Starting connection test for account ID: {twitter_account.id}")
        print(f"DEBUG: Raw auth_token from DB: {twitter_account.auth_token[:20]}...")
        print(f"DEBUG: Raw ct0_token from DB: {twitter_account.ct0_token[:20]}...")
        print(f"DEBUG: Cookies dict: {cookies}")
        
        # Run the async test
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(_test_connection_async(cookies))
            print(f"DEBUG: Connection test result: {result}")
            return result
        finally:
            loop.close()
    
    except ImportError:
        print("DEBUG: twikit import failed")
        return {
            'success': False,
            'error': 'twikit library not installed. Please run: pip install twikit'
        }
    except Exception as e:
        print(f"DEBUG: Connection test exception: {str(e)}")
        return {
            'success': False,
            'error': str(e)
        }

async def _test_connection_async(cookies):
    """Async function to test Twitter connection using your exact working code"""
    try:
        from twikit import Client
        
        # Debug: Print cookie values to check if they're extracted properly
        print(f"DEBUG: Testing connection with cookies: {cookies}")
        print(f"DEBUG: auth_token present: {'auth_token' in cookies}")
        print(f"DEBUG: ct0 present: {'ct0' in cookies}")
        if 'auth_token' in cookies:
            print(f"DEBUG: auth_token length: {len(cookies['auth_token'])}")
        if 'ct0' in cookies:
            print(f"DEBUG: ct0 length: {len(cookies['ct0'])}")
        
        # Initialize the client with cookies exactly like your working example
        client = Client(cookies=cookies, language='en-US')
        
        # Use the exact same approach as your working code
        try:
            # Get the authenticated user (your own account) - exactly like your code
            print("DEBUG: Attempting to get authenticated user...")
            me = await client.user()
            
            if me is None:
                print("DEBUG: client.user() returned None")
                return {
                    'success': False,
                    'error': 'Authentication failed - client.user() returned None'
                }
            
            print(f"DEBUG: Successfully authenticated as: @{me.screen_name}")
            
            # Try to fetch home timeline to further verify authentication
            try:
                print("DEBUG: Attempting to get latest timeline...")
                feed = await client.get_latest_timeline(count=1)  # Just get 1 tweet to test
                if feed:
                    print(f"DEBUG: Successfully got timeline with {len(feed)} tweets")
                    return {
                        'success': True,
                        'username': me.screen_name,
                        'display_name': getattr(me, 'name', me.screen_name),
                        'user_id': getattr(me, 'id', ''),
                        'method': 'authenticated_user'
                    }
                else:
                    print("DEBUG: Timeline is empty but auth worked")
                    return {
                        'success': True,
                        'username': me.screen_name,
                        'display_name': getattr(me, 'name', me.screen_name),
                        'user_id': getattr(me, 'id', ''),
                        'method': 'authenticated_user_only'
                    }
            except Exception as timeline_error:
                print(f"DEBUG: Timeline fetch failed: {str(timeline_error)}")
                # Still consider it successful if we got the authenticated user
                return {
                    'success': True,
                    'username': me.screen_name,
                    'display_name': getattr(me, 'name', me.screen_name),
                    'user_id': getattr(me, 'id', ''),
                    'method': 'authenticated_user_no_timeline'
                }
                
        except Exception as auth_error:
            print(f"DEBUG: Authentication failed with error: {str(auth_error)}")
            return {
                'success': False,
                'error': f'Authentication failed: {str(auth_error)}'
            }
    
    except Exception as e:
        print(f"DEBUG: Connection initialization failed: {str(e)}")
        return {
            'success': False,
            'error': f'Connection initialization failed: {str(e)}'
        }
