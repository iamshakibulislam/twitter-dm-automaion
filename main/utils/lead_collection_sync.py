"""
Synchronous Lead Collection Utilities
Uses subprocess to run twikit operations without async context issues
"""

import os
import sys
import django
import time
import random
import logging
import subprocess
import json
import tempfile
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'xoutreacher.settings')
django.setup()

from django.utils import timezone
from django.db import transaction, models
from django.contrib.auth.models import User
from main.models import LeadList, Lead, TwitterAccount
from django.conf import settings

logger = logging.getLogger(__name__)

def collect_leads_sync(
    lead_list_ids: Optional[List[int]] = None,
    max_lists: int = 5,
    force: bool = False,
    cleanup: bool = False,
    verbose: bool = True
) -> Dict[str, Any]:
    """
    Synchronous lead collection - uses subprocess for twikit operations
    """
    if verbose:
        print(f"🚀 Starting synchronous lead collection at {timezone.now()}")
    
    try:
        # Get lead lists for processing
        lead_lists = get_lead_lists_for_processing_sync(
            lead_list_ids=lead_list_ids,
            max_lists=max_lists,
            force=force,
            cleanup=cleanup
        )
        
        if not lead_lists:
            return {
                'success': True,
                'action': 'no_lists',
                'message': 'No lead lists to process',
                'processed_count': 0
            }
        
        if verbose:
            print(f"🎯 Selected {len(lead_lists)} lead list(s) for processing:")
            for lead_list in lead_lists:
                print(f"   ⏳ {lead_list.name} (ID: {lead_list.id}) - {lead_list.status}")
        
        # Process each lead list
        results = []
        for lead_list in lead_lists:
            try:
                result = process_single_lead_list_sync(lead_list, verbose)
                results.append({
                    'lead_list_id': lead_list.id,
                    **result
                })
            except Exception as e:
                error_msg = f"Error processing lead list {lead_list.id}: {str(e)}"
                logger.error(error_msg)
                if verbose:
                    print(f"❌ {error_msg}")
                
                results.append({
                    'lead_list_id': lead_list.id,
                    'success': False,
                    'message': str(e)
                })
        
        # Print summary
        if verbose:
            print_summary_sync(results)
        
        return {
            'success': True,
            'action': 'manual' if lead_list_ids else 'auto_discovery',
            'processed_lists': [r['lead_list_id'] for r in results],
            'results': results,
            'processed_count': len(results)
        }
        
    except Exception as e:
        error_msg = f"Lead collection error: {str(e)}"
        logger.error(error_msg)
        if verbose:
            print(f"❌ {error_msg}")
        
        return {
            'success': False,
            'error': str(e)
        }

def get_lead_lists_for_processing_sync(
    lead_list_ids: Optional[List[int]] = None,
    max_lists: int = 5,
    force: bool = False,
    cleanup: bool = False
) -> List[LeadList]:
    """Get lead lists ready for processing"""
    
    if cleanup:
        # Fix error states
        error_lists = LeadList.objects.filter(status='ERROR')
        for lead_list in error_lists:
            lead_list.status = 'PENDING'
            lead_list.error_message = ''
            lead_list.save()
        
        print(f"🔧 Cleaned up {len(error_lists)} error states")
    
    if lead_list_ids:
        # Specific lead lists
        queryset = LeadList.objects.filter(id__in=lead_list_ids)
    else:
        # Auto-discover active lists
        queryset = LeadList.objects.filter(
            status__in=['PENDING', 'COLLECTING']
        ).exclude(total_collected__gte=models.F('max_leads'))
    
    # Apply limits and ordering
    lead_lists = list(queryset.order_by('-created_at')[:max_lists])
    
    if not force:
        # Filter by time (20-minute interval)
        now = timezone.now()
        lead_lists = [
            ll for ll in lead_lists 
            if not ll.last_processed_at or 
            (now - ll.last_processed_at) >= timedelta(minutes=20)
        ]
    
    return lead_lists

def process_single_lead_list_sync(lead_list: LeadList, verbose: bool = True) -> Dict[str, Any]:
    """Process a single lead list synchronously using subprocess for twikit"""
    
    if verbose:
        print(f"⚙️  Processing lead list: {lead_list.name} (ID: {lead_list.id})")
    
    try:
        # Check if we can collect more
        if not can_collect_more_sync(lead_list):
            return {
                'success': False,
                'message': 'Lead list has reached maximum capacity or is not active'
            }
        
        # Get available Twitter account
        twitter_account = get_available_twitter_account_sync(lead_list.user)
        if not twitter_account:
            return {
                'success': False,
                'message': 'No verified Twitter accounts available'
            }
        
        if verbose:
            print(f"   📱 Using Twitter account: @{twitter_account.username}")
        
        # Update status
        with transaction.atomic():
            lead_list.status = 'COLLECTING'
            lead_list.last_processed_at = timezone.now()
            lead_list.save()
        
        # Actually collect leads using twikit via subprocess
        collected_count = collect_leads_with_twikit_sync(lead_list, twitter_account, verbose)
        
        # Update final status
        with transaction.atomic():
            lead_list.refresh_from_db()
            lead_list.total_collected = Lead.objects.filter(lead_list=lead_list).count()
            
            if lead_list.total_collected >= lead_list.max_leads:
                lead_list.status = 'COMPLETED'
            elif collected_count == 0:
                lead_list.status = 'PAUSED'
            else:
                lead_list.status = 'COLLECTING'
            
            lead_list.last_processed_at = timezone.now()
            lead_list.save()
        
        return {
            'success': True,
            'collected': collected_count,
            'processed': collected_count,  # For now, processed = collected
            'total_leads': lead_list.total_collected,
            'status': lead_list.status,
            'account_used': twitter_account.username
        }
        
    except Exception as e:
        # Mark as error
        with transaction.atomic():
            lead_list.status = 'ERROR'
            lead_list.error_message = str(e)
            lead_list.save()
        
        raise e

def can_collect_more_sync(lead_list: LeadList) -> bool:
    """Check if lead list can collect more leads"""
    return (
        lead_list.status in ['PENDING', 'COLLECTING'] and
        lead_list.total_collected < lead_list.max_leads
    )

def get_available_twitter_account_sync(user: User) -> Optional[TwitterAccount]:
    """Get an available Twitter account for the user"""
    return TwitterAccount.objects.filter(
        user=user,
        is_verified=True,
        is_active=True
    ).order_by('-last_verified').first()

def collect_leads_with_twikit_sync(lead_list: LeadList, twitter_account: TwitterAccount, verbose: bool = True) -> int:
    """
    Collect leads using twikit via subprocess to avoid async issues
    """
    if verbose:
        print(f"   🔄 Starting actual lead collection with twikit")
        print(f"   📊 Target sources: {len(lead_list.target_usernames)} usernames, {len(lead_list.target_post_urls)} posts")
    
    collected_count = 0
    
    try:
        # Collect from followers
        if lead_list.target_usernames:
            for username in lead_list.target_usernames:
                if verbose:
                    print(f"   👥 Collecting followers from @{username}")
                
                followers = collect_followers_sync(username, twitter_account, lead_list, verbose)
                collected_count += followers
                
                # Add delay between usernames
                time.sleep(random.uniform(1, 3))
        
        # Collect from commenters
        if lead_list.target_post_urls:
            for post_url in lead_list.target_post_urls:
                if verbose:
                    print(f"   💬 Collecting commenters from {post_url}")
                
                commenters = collect_commenters_sync(post_url, twitter_account, lead_list, verbose)
                collected_count += commenters
                
                # Add delay between posts
                time.sleep(random.uniform(1, 3))
        
        if verbose:
            print(f"   ✅ Collection completed: {collected_count} new leads")
        
        return collected_count
        
    except Exception as e:
        if verbose:
            print(f"   ❌ Error during collection: {str(e)}")
        logger.error(f"Error collecting leads for list {lead_list.id}: {str(e)}")
        return 0

def collect_followers_sync(username: str, twitter_account: TwitterAccount, lead_list: LeadList, verbose: bool = True) -> int:
    """Collect followers for a specific username using subprocess"""
    try:
        # Create a temporary Python script to run twikit
        script_content = f'''
import asyncio
import json
import sys
from twikit import Client

async def collect_followers():
    try:
        # Setup client
        cookies = {json.dumps(twitter_account.get_cookies_dict())}
        client = Client(cookies=cookies, language='en-US')
        
        # Get user
        user = await client.get_user_by_screen_name('{username}')
        if not user:
            return {{"error": "User not found"}}
        
        # Get user info first
        user_followers_count = getattr(user, 'followers_count', 0)
        
        # Get followers
        followers_result = await user.get_followers(count=200)
        followers = []
        
        # Process first batch
        for follower in followers_result:
            if len(followers) >= 200:  # Limit batch size
                break
                
            follower_data = {{
                'username': getattr(follower, 'screen_name', ''),
                'display_name': getattr(follower, 'name', ''),
                'bio': getattr(follower, 'description', ''),
                'location': getattr(follower, 'location', ''),
                'followers_count': getattr(follower, 'followers_count', 0),
                'following_count': getattr(follower, 'friends_count', 0),
                'tweet_count': getattr(follower, 'statuses_count', 0),
                'profile_image_url': getattr(follower, 'profile_image_url_https', ''),
                'verified': getattr(follower, 'verified', False),
            }}
            followers.append(follower_data)
        
        # Try to get more pages to estimate total available
        total_available = 0
        try:
            for _ in range(4):  # Get up to 5 pages (1000 followers)
                followers_result = await followers_result.next()
                for follower in followers_result:
                    if len(followers) >= 1000:  # Hard limit for collection
                        break
                        
                    follower_data = {{
                        'username': getattr(follower, 'screen_name', ''),
                        'display_name': getattr(follower, 'name', ''),
                        'bio': getattr(follower, 'description', ''),
                        'location': getattr(follower, 'location', ''),
                        'followers_count': getattr(follower, 'followers_count', 0),
                        'following_count': getattr(follower, 'friends_count', 0),
                        'tweet_count': getattr(follower, 'statuses_count', 0),
                        'profile_image_url': getattr(follower, 'profile_image_url_https', ''),
                        'verified': getattr(follower, 'verified', False),
                    }}
                    followers.append(follower_data)
                    
                if len(followers) >= 1000:
                    break
                    
                await asyncio.sleep(1)  # Rate limiting
                
        except Exception as e:
            pass  # No more pages
        
        # Estimate total available leads (this user's followers count)
        total_available = user_followers_count
        
        return {{"success": True, "followers": followers, "count": len(followers), "total_available": total_available}}
        
    except Exception as e:
        return {{"error": str(e)}}

# Run the async function
result = asyncio.run(collect_followers())
print(json.dumps(result))
'''
        
        # Write script to temporary file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write(script_content)
            script_path = f.name
        
        try:
            # Run the script
            if verbose:
                print(f"      🚀 Running twikit collection script...")
            
            result = subprocess.run(
                [sys.executable, script_path],
                capture_output=True,
                text=True,
                timeout=300  # 5 minute timeout
            )
            
            if result.returncode == 0:
                try:
                    data = json.loads(result.stdout.strip())
                    if data.get('success'):
                        followers = data.get('followers', [])
                        count = data.get('count', 0)
                        total_available = data.get('total_available', 0)
                        
                        if verbose:
                            print(f"      ✅ Collected {count} followers from @{username}")
                            print(f"      📊 Estimated total available: {total_available} followers")
                        
                        # Update estimated total leads
                        if total_available > 0:
                            lead_list.update_estimated_total(total_available)
                        
                        # Save followers to database
                        saved_count = save_followers_to_db(lead_list, followers, username, verbose)
                        return saved_count
                    else:
                        if verbose:
                            print(f"      ❌ Error: {data.get('error', 'Unknown error')}")
                        return 0
                except json.JSONDecodeError:
                    if verbose:
                        print(f"      ❌ Invalid JSON response: {result.stdout}")
                    return 0
            else:
                if verbose:
                    print(f"      ❌ Script failed: {result.stderr}")
                return 0
                
        finally:
            # Clean up temporary file
            try:
                os.unlink(script_path)
            except:
                pass
                
    except Exception as e:
        if verbose:
            print(f"      ❌ Error collecting followers: {str(e)}")
        return 0

def collect_commenters_sync(post_url: str, twitter_account: TwitterAccount, lead_list: LeadList, verbose: bool = True) -> int:
    """Collect commenters for a specific post using subprocess"""
    try:
        # Extract tweet ID from URL
        tweet_id = extract_tweet_id_from_url(post_url)
        if not tweet_id:
            if verbose:
                print(f"      ❌ Could not extract tweet ID from URL: {post_url}")
            return 0
        
        # Create a temporary Python script to run twikit
        script_content = f'''
import asyncio
import json
import sys
from twikit import Client

async def collect_commenters():
    try:
        # Setup client
        cookies = {json.dumps(twitter_account.get_cookies_dict())}
        client = Client(cookies=cookies, language='en-US')
        
        # Get tweet comments
        comments_result = await client.get_tweet_comments('{tweet_id}', count=200)
        commenters = []
        
        # Process first batch
        for comment in comments_result:
            if len(commenters) >= 200:  # Limit batch size
                break
                
            user = comment.user
            commenter_data = {{
                'username': getattr(user, 'screen_name', ''),
                'display_name': getattr(user, 'name', ''),
                'bio': getattr(user, 'description', ''),
                'location': getattr(user, 'location', ''),
                'followers_count': getattr(user, 'followers_count', 0),
                'following_count': getattr(user, 'friends_count', 0),
                'tweet_count': getattr(user, 'statuses_count', 0),
                'profile_image_url': getattr(user, 'profile_image_url_https', ''),
                'verified': getattr(user, 'verified', False),
            }}
            commenters.append(commenter_data)
        
        # Try to get more pages
        try:
            for _ in range(4):  # Get up to 5 pages (1000 commenters)
                comments_result = await comments_result.next()
                for comment in comments_result:
                    if len(commenters) >= 1000:  # Hard limit
                        break
                        
                    user = comment.user
                    commenter_data = {{
                        'username': getattr(user, 'screen_name', ''),
                        'display_name': getattr(user, 'name', ''),
                        'bio': getattr(user, 'description', ''),
                        'location': getattr(user, 'location', ''),
                        'followers_count': getattr(user, 'followers_count', 0),
                        'following_count': getattr(user, 'friends_count', 0),
                        'tweet_count': getattr(user, 'statuses_count', 0),
                        'profile_image_url': getattr(user, 'profile_image_url_https', ''),
                        'verified': getattr(user, 'verified', False),
                    }}
                    commenters.append(commenter_data)
                    
                if len(commenters) >= 1000:
                    break
                    
                await asyncio.sleep(1)  # Rate limiting
                
        except Exception as e:
            pass  # No more pages
        
        # Estimate total available leads (this tweet's engagement)
        total_available = len(commenters)  # For now, use collected count as estimate
        
        return {{"success": True, "commenters": commenters, "count": len(commenters), "total_available": total_available}}
        
    except Exception as e:
        return {{"error": str(e)}}

# Run the async function
result = asyncio.run(collect_commenters())
print(json.dumps(result))
'''
        
        # Write script to temporary file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write(script_content)
            script_path = f.name
        
        try:
            # Run the script
            if verbose:
                print(f"      🚀 Running twikit collection script for tweet {tweet_id}...")
            
            result = subprocess.run(
                [sys.executable, script_path],
                capture_output=True,
                text=True,
                timeout=300  # 5 minute timeout
            )
            
            if result.returncode == 0:
                try:
                    data = json.loads(result.stdout.strip())
                    if data.get('success'):
                        commenters = data.get('commenters', [])
                        count = data.get('count', 0)
                        total_available = data.get('total_available', 0)
                        
                        if verbose:
                            print(f"      ✅ Collected {count} commenters from tweet {tweet_id}")
                            print(f"      📊 Estimated total available: {total_available} commenters")
                        
                        # Update estimated total leads
                        if total_available > 0:
                            lead_list.update_estimated_total(total_available)
                        
                        # Save commenters to database
                        saved_count = save_commenters_to_db(lead_list, commenters, post_url, verbose)
                        return saved_count
                    else:
                        if verbose:
                            print(f"      ❌ Error: {data.get('error', 'Unknown error')}")
                        return 0
                except json.JSONDecodeError:
                    if verbose:
                        print(f"      ❌ Invalid JSON response: {result.stdout}")
                    return 0
            else:
                if verbose:
                    print(f"      ❌ Script failed: {result.stderr}")
                return 0
                
        finally:
            # Clean up temporary file
            try:
                os.unlink(script_path)
            except:
                pass
                
    except Exception as e:
        if verbose:
            print(f"      ❌ Error collecting commenters: {str(e)}")
        return 0

def extract_tweet_id_from_url(post_url: str) -> Optional[str]:
    """Extract tweet ID from Twitter URL"""
    import re
    pattern = r'https?://(twitter\.com|x\.com)/.+/status/(\d+)'
    match = re.search(pattern, post_url)
    return match.group(2) if match else None

def save_followers_to_db(lead_list: LeadList, followers: List[Dict], source_username: str, verbose: bool = True) -> int:
    """Save followers to database with filtering"""
    saved_count = 0
    
    for follower_data in followers:
        try:
            # Apply filters
            if not matches_filters_sync(follower_data, lead_list):
                continue
            
            # Check if already exists
            if Lead.objects.filter(lead_list=lead_list, username=follower_data['username']).exists():
                continue
            
            # Save lead
            lead = Lead.objects.create(
                lead_list=lead_list,
                username=follower_data['username'],
                display_name=follower_data['display_name'],
                bio=follower_data['bio'],
                location=follower_data['location'],
                followers_count=follower_data['followers_count'],
                following_count=follower_data['following_count'],
                tweet_count=follower_data['tweet_count'],
                profile_image_url=follower_data['profile_image_url'],
                verified=follower_data['verified'],
                source_type='FOLLOWER',
                source_reference=source_username
            )
            saved_count += 1
            
        except Exception as e:
            if verbose:
                print(f"         ⚠️  Error saving follower {follower_data.get('username', 'unknown')}: {str(e)}")
            continue
    
    if verbose:
        print(f"         💾 Saved {saved_count} new leads to database")
    
    return saved_count

def save_commenters_to_db(lead_list: LeadList, commenters: List[Dict], source_post: str, verbose: bool = True) -> int:
    """Save commenters to database with filtering"""
    saved_count = 0
    
    for commenter_data in commenters:
        try:
            # Apply filters
            if not matches_filters_sync(commenter_data, lead_list):
                continue
            
            # Check if already exists
            if Lead.objects.filter(lead_list=lead_list, username=commenter_data['username']).exists():
                continue
            
            # Save lead
            lead = Lead.objects.create(
                lead_list=lead_list,
                username=commenter_data['username'],
                display_name=commenter_data['display_name'],
                bio=commenter_data['bio'],
                location=commenter_data['location'],
                followers_count=commenter_data['followers_count'],
                following_count=commenter_data['following_count'],
                tweet_count=commenter_data['tweet_count'],
                profile_image_url=commenter_data['profile_image_url'],
                verified=commenter_data['verified'],
                source_type='COMMENTER',
                source_reference=source_post
            )
            saved_count += 1
            
        except Exception as e:
            if verbose:
                print(f"         ⚠️  Error saving commenter {commenter_data.get('username', 'unknown')}: {str(e)}")
            continue
    
    if verbose:
        print(f"         💾 Saved {saved_count} new leads to database")
    
    return saved_count

def matches_filters_sync(user_data: Dict, lead_list: LeadList) -> bool:
    """Check if user matches the lead list filters"""
    try:
        # Follower count filter
        follower_count = user_data.get('followers_count', 0)
        if follower_count < lead_list.min_followers or follower_count > lead_list.max_followers:
            return False
        
        # Location filter (if specified, user must match)
        if lead_list.locations:
            user_location = user_data.get('location', '') or ''
            location_match = any(
                location.lower() in user_location.lower() 
                for location in lead_list.locations
            )
            if not location_match:
                return False
        
        # Bio keyword filters
        user_bio = user_data.get('bio', '') or ''
        user_bio_lower = user_bio.lower()
        
        # Include keywords (if specified, user must match)
        if lead_list.bio_keywords:
            keyword_match = any(
                keyword in user_bio_lower 
                for keyword in lead_list.bio_keywords
            )
            if not keyword_match:
                return False
        
        # Exclude keywords
        if lead_list.exclude_keywords:
            exclude_match = any(
                keyword in user_bio_lower 
                for keyword in lead_list.exclude_keywords
            )
            if exclude_match:
                return False
        
        return True
        
    except Exception as e:
        logger.error(f"Error checking filters for user: {str(e)}")
        return False

def print_summary_sync(results: List[Dict[str, Any]]):
    """Print collection summary"""
    print("\n📊 Collection Results Summary:")
    print("=" * 50)
    
    successful = [r for r in results if r.get('success')]
    failed = [r for r in results if not r.get('success')]
    
    for result in results:
        if result.get('success'):
            print(f"✅ Lead List {result['lead_list_id']}: Collected {result.get('collected', 0)} new leads")
            print(f"   📊 Total leads: {result.get('total_leads', 0)}, Status: {result.get('status', 'UNKNOWN')}, Account: @{result.get('account_used', 'unknown')}")
        else:
            print(f"❌ Lead List {result['lead_list_id']}: {result.get('message', 'Unknown error')}")
    
    print("=" * 50)
    print(f"🎯 Overall: {len(successful)}/{len(results)} lists processed successfully")
    
    total_collected = sum(r.get('collected', 0) for r in successful)
    print(f"📈 Total: {total_collected} new leads collected")

def get_stats_sync() -> Dict[str, Any]:
    """Get system statistics"""
    now = timezone.now()
    
    return {
        'total_lead_lists': LeadList.objects.count(),
        'active_lead_lists': LeadList.objects.filter(status__in=['PENDING', 'COLLECTING']).count(),
        'completed_lead_lists': LeadList.objects.filter(status='COMPLETED').count(),
        'error_lead_lists': LeadList.objects.filter(status='ERROR').count(),
        'paused_lead_lists': LeadList.objects.filter(status='PAUSED').count(),
        'total_leads': Lead.objects.count(),
        'recent_activity': LeadList.objects.filter(
            last_processed_at__gte=now - timedelta(hours=1)
        ).count(),
        'total_twitter_accounts': TwitterAccount.objects.filter(is_verified=True, is_active=True).count(),
    }

# Main function for easy import
def collect_leads(
    lead_list_ids: Optional[List[int]] = None,
    max_lists: int = 5,
    force: bool = False,
    cleanup: bool = False,
    verbose: bool = True
) -> Dict[str, Any]:
    """Main function - alias for collect_leads_sync"""
    return collect_leads_sync(
        lead_list_ids=lead_list_ids,
        max_lists=max_lists,
        force=force,
        cleanup=cleanup,
        verbose=verbose
    )

def get_stats() -> Dict[str, Any]:
    """Get stats - alias for get_stats_sync"""
    return get_stats_sync()

if __name__ == "__main__":
    # Test the functions
    print("Testing synchronous lead collection...")
    
    # Get stats
    stats = get_stats_sync()
    print(f"System stats: {stats}")
    
    # Try to collect leads
    result = collect_leads_sync(max_lists=1, force=True, verbose=True)
    print(f"Collection result: {result}")
