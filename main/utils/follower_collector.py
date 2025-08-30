"""
Simple Follower Collection System
Inspired by working twikit code - clean and straightforward
"""
import asyncio
import json
import logging
from typing import List, Dict, Any, Optional
from django.utils import timezone
from django.db import transaction, models
from django.contrib.auth.models import User
from main.models import LeadList, Lead, TwitterAccount
from twikit import Client

logger = logging.getLogger(__name__)

class SimpleFollowerCollector:
    """Simple follower collection using twikit with progress tracking"""
    
    def __init__(self):
        self.chunk_size = 1000  # Fetch up to 1000 followers per run
        
    async def collect_followers_for_list(self, lead_list_id: int, verbose: bool = True) -> Dict[str, Any]:
        """Collect followers for a specific lead list"""
        try:
            # Get the lead list
            lead_list = LeadList.objects.get(id=lead_list_id)
            
            if verbose:
                print(f"🚀 Starting follower collection for: {lead_list.name}")
                print(f"📊 Target usernames: {lead_list.target_usernames}")
            
            # Get Twitter account
            twitter_account = TwitterAccount.objects.filter(
                user=lead_list.user,
                is_verified=True,
                is_active=True
            ).first()
            
            if not twitter_account:
                return {
                    'success': False,
                    'message': 'No verified Twitter account available'
                }
            
            if verbose:
                print(f"📱 Using Twitter account: @{twitter_account.username}")
            
            # Update status
            lead_list.status = 'COLLECTING'
            lead_list.last_processed_at = timezone.now()
            lead_list.save()
            
            total_collected = 0
            all_followers_data = []  # Store all data in memory
            
            # Collect from each target username
            for username in lead_list.target_usernames:
                if verbose:
                    print(f"\n👥 Collecting followers from @{username}")
                
                # Collect followers data (no database operations here)
                followers_data = await self._collect_followers_chunk_data(
                    username, 
                    lead_list, 
                    twitter_account, 
                    verbose
                )
                
                if followers_data:
                    all_followers_data.extend(followers_data)
                    total_collected += len(followers_data)
                
                if verbose:
                    print(f"✅ Collected {len(followers_data) if followers_data else 0} followers from @{username}")
            
            # Now save all collected data to database at once
            if all_followers_data:
                if verbose:
                    print(f"\n💾 Saving {len(all_followers_data)} followers to database...")
                
                saved_count = self._save_followers_batch(lead_list, all_followers_data, verbose)
                
                if verbose:
                    print(f"💾 Successfully saved {saved_count} followers to database")
                
                # Update pagination state for all usernames
                self._update_pagination_state(lead_list, all_followers_data, verbose)
            
            # Update final status
            lead_list.total_collected = Lead.objects.filter(lead_list=lead_list).count()
            lead_list.status = 'COMPLETED' if total_collected > 0 else 'PAUSED'
            lead_list.last_processed_at = timezone.now()
            lead_list.save()
            
            if verbose:
                print(f"\n🎉 Collection completed! Total new leads: {total_collected}")
            
            return {
                'success': True,
                'collected': total_collected,
                'total_leads': lead_list.total_collected,
                'status': lead_list.status
            }
            
        except Exception as e:
            logger.error(f"Error collecting followers for list {lead_list_id}: {str(e)}")
            
            # Mark as error
            try:
                lead_list = LeadList.objects.get(id=lead_list_id)
                lead_list.status = 'ERROR'
                lead_list.error_message = str(e)
                lead_list.save()
            except:
                pass
            
            return {
                'success': False,
                'message': str(e)
            }
    
    async def _collect_followers_chunk_data(
        self, 
        screen_name: str, 
        lead_list: LeadList, 
        twitter_account: TwitterAccount, 
        verbose: bool = True
    ) -> List[Dict]:
        """Collect followers data without saving to database - returns list of follower data"""
        try:
            # Initialize client
            client = Client(
                cookies=twitter_account.get_cookies_dict(), 
                language='en-US'
            )
            
            # Get user info
            user = await client.get_user_by_screen_name(screen_name)
            if not user:
                if verbose:
                    print(f"❌ User @{screen_name} not found")
                return []
            
            if verbose:
                print(f"📊 @{screen_name} has {getattr(user, 'followers_count', 0)} followers")
            
            # Load progress from pagination state
            pagination_state = lead_list.pagination_state or {}
            user_state = pagination_state.get(screen_name, {})
            cursor = user_state.get('cursor')
            collected_so_far = user_state.get('collected', 0)
            
            if verbose:
                print(f"🔄 Resuming from cursor: {cursor}")
                print(f"📈 Already collected: {collected_so_far} followers")
            
            new_cursor = cursor
            run_followers = []  # New ones this run
            
            # Keep paging until we hit CHUNK_SIZE
            while len(run_followers) < self.chunk_size:
                if new_cursor:
                    result = await client.get_latest_followers(
                        screen_name=screen_name,
                        count=100,  # Request 100 per page (max twikit allows)
                        cursor=new_cursor
                    )
                else:
                    result = await client.get_latest_followers(
                        screen_name=screen_name,
                        count=100
                    )
                
                followers = list(result)
                new_cursor = result.next_cursor
                
                if not followers:
                    if verbose:
                        print("📄 No more followers available")
                    break
                
                for follower in followers:
                    # Create follower data (no database check here)
                    follower_data = {
                        'username': getattr(follower, 'screen_name', ''),
                        'display_name': getattr(follower, 'name', ''),
                        'bio': getattr(follower, 'description', ''),
                        'location': getattr(follower, 'location', ''),
                        'followers_count': getattr(follower, 'followers_count', 0),
                        'following_count': getattr(follower, 'friends_count', 0),
                        'tweet_count': getattr(follower, 'statuses_count', 0),
                        'profile_image_url': getattr(follower, 'profile_image_url_https', ''),
                        'verified': getattr(follower, 'verified', False),
                        'source_type': 'FOLLOWER',
                        'source_reference': screen_name,
                        'pagination_cursor': new_cursor,  # Store cursor for later
                        'pagination_collected': collected_so_far + len(run_followers) + 1
                    }
                    
                    run_followers.append(follower_data)
                    
                    if verbose and len(run_followers) <= 5:
                        print(f"  📝 @{follower_data['username']} - {follower_data['followers_count']} followers")
                    
                    if len(run_followers) >= self.chunk_size:
                        break
                
                if not new_cursor:  # No more pages
                    break
            
            if verbose:
                print(f"📊 Fetched {len(run_followers)} followers this run")
                print(f"🔑 Next cursor: {new_cursor}")
                print(f"🔄 Has more pages: {new_cursor is not None}")
            
            return run_followers
            
        except Exception as e:
            if verbose:
                print(f"❌ Error collecting followers from @{screen_name}: {str(e)}")
            logger.error(f"Error collecting followers from @{screen_name}: {str(e)}")
            return []
    
    def _save_followers_batch(self, lead_list: LeadList, followers_data: List[Dict], verbose: bool = True) -> int:
        """Save all followers to database in a batch - synchronous function"""
        saved_count = 0
        duplicate_count = 0
        
        if verbose:
            print(f"         💾 Starting batch save of {len(followers_data)} followers...")
        
        for i, follower_data in enumerate(followers_data):
            try:
                # Check if already exists
                if Lead.objects.filter(lead_list=lead_list, username=follower_data['username']).exists():
                    duplicate_count += 1
                    if verbose and duplicate_count <= 3:
                        print(f"         🔄 Duplicate found: @{follower_data['username']}")
                    continue
                
                # Remove pagination fields before saving
                save_data = {k: v for k, v in follower_data.items() 
                           if k not in ['pagination_cursor', 'pagination_collected']}
                
                # Save lead
                lead = Lead.objects.create(
                    lead_list=lead_list,
                    **save_data
                )
                saved_count += 1
                
                if verbose and saved_count <= 5:
                    print(f"         ✅ Saved @{follower_data['username']} (ID: {lead.id})")
                
            except Exception as e:
                if verbose:
                    print(f"         ❌ Error saving @{follower_data.get('username', 'unknown')}: {str(e)}")
                continue
        
        if verbose:
            print(f"         📊 Batch save completed: {saved_count} saved, {duplicate_count} duplicates")
        
        return saved_count
    
    def _update_pagination_state(self, lead_list: LeadList, followers_data: List[Dict], verbose: bool = True):
        """Update pagination state for all usernames - synchronous function"""
        try:
            pagination_state = lead_list.pagination_state or {}
            
            # Group followers by source username
            username_groups = {}
            for follower in followers_data:
                username = follower['source_reference']
                if username not in username_groups:
                    username_groups[username] = []
                username_groups[username].append(follower)
            
            # Update pagination state for each username
            for username, followers in username_groups.items():
                if followers:
                    last_follower = followers[-1]
                    cursor = last_follower.get('pagination_cursor')
                    collected = last_follower.get('pagination_collected', 0)
                    
                    pagination_state[username] = {
                        'cursor': cursor,
                        'collected': collected,
                        'has_more': cursor is not None,
                        'last_updated': timezone.now().isoformat()
                    }
            
            lead_list.pagination_state = pagination_state
            lead_list.save(update_fields=['pagination_state'])
            
            if verbose:
                print(f"         🔄 Updated pagination state for {len(username_groups)} usernames")
                
        except Exception as e:
            if verbose:
                print(f"         ⚠️  Error updating pagination state: {str(e)}")

def reset_lead_list_status(lead_list_id: int, verbose: bool = True) -> Dict[str, Any]:
    """
    Reset a lead list status to PENDING so it can continue collecting
    Useful when a list is marked as COMPLETED but you want to collect more
    """
    try:
        lead_list = LeadList.objects.get(id=lead_list_id)
        
        if verbose:
            print(f"🔄 Resetting status for: {lead_list.name} (ID: {lead_list.id})")
            print(f"   Current status: {lead_list.status}")
            print(f"   Current collected: {lead_list.total_collected}")
            print(f"   Max leads: {lead_list.max_leads}")
        
        # Reset status to PENDING
        lead_list.status = 'PENDING'
        lead_list.save(update_fields=['status'])
        
        if verbose:
            print(f"   ✅ Status reset to PENDING")
            print(f"   🔄 Ready for continued collection")
        
        return {
            'success': True,
            'message': f'Lead list {lead_list.name} reset to PENDING',
            'lead_list_id': lead_list.id,
            'new_status': 'PENDING'
        }
        
    except LeadList.DoesNotExist:
        return {
            'success': False,
            'message': f'Lead list with ID {lead_list_id} not found'
        }
    except Exception as e:
        return {
            'success': False,
            'message': f'Error resetting status: {str(e)}'
        }

# Global instance
follower_collector = SimpleFollowerCollector()

# Convenience function for Django shell testing
async def collect_followers(lead_list_id: int, verbose: bool = True) -> Dict[str, Any]:
    """Simple function to collect followers for testing"""
    return await follower_collector.collect_followers_for_list(lead_list_id, verbose)

# Synchronous wrapper for Django shell
def collect_followers_sync(lead_list_id: int, verbose: bool = True) -> Dict[str, Any]:
    """Synchronous wrapper for Django shell testing"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        result = loop.run_until_complete(collect_followers(lead_list_id, verbose))
        return result
    finally:
        loop.close()

# Function for cron jobs - automatically processes multiple lead lists
def collect_followers_cron(lead_list_id: int = None, verbose: bool = False) -> Dict[str, Any]:
    """
    Completely synchronous function for cron jobs that processes all lead lists
    No async calls - everything is done synchronously
    """
    try:
        if verbose:
            print(f"🚀 Starting cron follower collection at {timezone.now()}")
        
        if lead_list_id:
            # Process specific lead list
            lead_lists = [LeadList.objects.get(id=lead_list_id)]
        else:
            # Get all pending lead lists
            lead_lists = list(LeadList.objects.filter(
                status__in=['PENDING', 'COLLECTING', 'PAUSED']
            ).exclude(total_collected__gte=models.F('max_leads'))[:5])
        
        if not lead_lists:
            # Get more detailed information about why no lists are being processed
            all_lists = LeadList.objects.all()
            completed_lists = all_lists.filter(status='COMPLETED')
            pending_lists = all_lists.filter(status='PENDING')
            collecting_lists = all_lists.filter(status='COLLECTING')
            paused_lists = all_lists.filter(status='PAUSED')
            error_lists = all_lists.filter(status='ERROR')
            
            if verbose:
                print(f"📊 Lead List Status Summary:")
                print(f"   Total: {all_lists.count()}")
                print(f"   PENDING: {pending_lists.count()}")
                print(f"   COLLECTING: {collecting_lists.count()}")
                print(f"   PAUSED: {paused_lists.count()}")
                print(f"   COMPLETED: {completed_lists.count()}")
                print(f"   ERROR: {error_lists.count()}")
                
                # Show some examples
                if paused_lists.exists():
                    print(f"\n⏸️  PAUSED lists (can continue collecting):")
                    for ll in paused_lists[:3]:
                        print(f"   - {ll.name} (ID: {ll.id}) - {ll.total_collected}/{ll.max_leads} leads")
                
                if completed_lists.exists():
                    print(f"\n✅ COMPLETED lists (reached max_leads):")
                    for ll in completed_lists[:3]:
                        print(f"   - {ll.name} (ID: {ll.id}) - {ll.total_collected}/{ll.max_leads} leads")
            
            return {
                'success': True,
                'action': 'no_lists',
                'message': 'No lead lists to process',
                'processed_count': 0,
                'status_summary': {
                    'total': all_lists.count(),
                    'pending': pending_lists.count(),
                    'collecting': collecting_lists.count(),
                    'paused': paused_lists.count(),
                    'completed': completed_lists.count(),
                    'error': error_lists.count()
                }
            }
        
        if verbose:
            print(f"🎯 Processing {len(lead_lists)} lead list(s)")
        
        results = []
        total_collected = 0
        
        for lead_list in lead_lists:
            try:
                if verbose:
                    print(f"\n⚙️  Processing: {lead_list.name} (ID: {lead_list.id})")
                
                # Process this lead list completely synchronously
                result = process_lead_list_sync(lead_list, verbose=verbose)
                results.append({
                    'lead_list_id': lead_list.id,
                    'name': lead_list.name,
                    **result
                })
                
                if result['success']:
                    total_collected += result.get('collected', 0)
                
            except Exception as e:
                error_msg = f"Error processing lead list {lead_list.id}: {str(e)}"
                logger.error(error_msg)
                if verbose:
                    print(f"❌ {error_msg}")
                
                results.append({
                    'lead_list_id': lead_list.id,
                    'name': lead_list.name,
                    'success': False,
                    'message': str(e)
                })
        
        if verbose:
            print(f"🎉 Cron collection completed! Total new leads: {total_collected}")
            print(f"📊 Results: {len([r for r in results if r.get('success')])}/{len(results)} successful")
        
        return {
            'success': True,
            'action': 'cron',
            'processed_lists': [r['lead_list_id'] for r in results],
            'results': results,
            'total_collected': total_collected,
            'processed_count': len(results)
        }
        
    except Exception as e:
        error_msg = f"Cron collection error: {str(e)}"
        logger.error(error_msg)
        if verbose:
            print(f"❌ {error_msg}")
        
        return {
            'success': False,
            'error': str(e)
        }

def process_lead_list_sync(lead_list: LeadList, verbose: bool = True) -> Dict[str, Any]:
    """
    Completely synchronous function to process a single lead list
    No async calls - everything is done synchronously
    """
    try:
        if verbose:
            print(f"   🚀 Starting follower collection for: {lead_list.name}")
            print(f"   📊 Target usernames: {lead_list.target_usernames}")
        
        # Get Twitter account
        twitter_account = TwitterAccount.objects.filter(
            user=lead_list.user,
            is_verified=True,
            is_active=True
        ).first()
        
        if not twitter_account:
            return {
                'success': False,
                'message': 'No verified Twitter account available'
            }
        
        if verbose:
            print(f"   📱 Using Twitter account: @{twitter_account.username}")
        
        # Update status
        lead_list.status = 'COLLECTING'
        lead_list.last_processed_at = timezone.now()
        lead_list.save()
        
        total_collected = 0
        all_followers_data = []  # Store all data in memory
        
        # Collect from each target username
        for username in lead_list.target_usernames:
            if verbose:
                print(f"   👥 Collecting followers from @{username}")
            
            # Collect followers data using subprocess (no async)
            followers_data = collect_followers_with_subprocess(
                username, 
                twitter_account, 
                lead_list,  # Pass lead_list to access pagination state
                verbose
            )
            
            if followers_data:
                all_followers_data.extend(followers_data)
                total_collected += len(followers_data)
            
            if verbose:
                print(f"   ✅ Collected {len(followers_data) if followers_data else 0} followers from @{username}")
        
        # Now save all collected data to database at once
        if all_followers_data:
            if verbose:
                print(f"   💾 Saving {len(all_followers_data)} followers to database...")
            
            saved_count = _save_followers_batch(lead_list, all_followers_data, verbose)
            
            if verbose:
                print(f"   💾 Successfully saved {saved_count} followers to database")
            
            # Update pagination state for all usernames
            _update_pagination_state(lead_list, all_followers_data, verbose)
        
        # Update final status - check if we can collect more
        lead_list.total_collected = Lead.objects.filter(lead_list=lead_list).count()
        
        # Check if we have more pages available for any username
        has_more_pages = False
        if all_followers_data:
            for follower in all_followers_data:
                if follower.get('pagination_cursor'):
                    has_more_pages = True
                    break
        
        # Set status based on whether we can collect more
        if lead_list.total_collected >= lead_list.max_leads:
            lead_list.status = 'COMPLETED'
        elif has_more_pages and total_collected > 0:
            lead_list.status = 'PAUSED'  # More pages available, can continue later
        elif total_collected == 0:
            lead_list.status = 'PAUSED'  # No new leads collected
        else:
            lead_list.status = 'COLLECTING'  # Still collecting
        
        lead_list.last_processed_at = timezone.now()
        lead_list.save()
        
        if verbose:
            print(f"   🎉 Collection completed! Total new leads: {total_collected}")
        
        return {
            'success': True,
            'collected': total_collected,
            'total_leads': lead_list.total_collected,
            'status': lead_list.status
        }
        
    except Exception as e:
        logger.error(f"Error processing lead list {lead_list.id}: {str(e)}")
        
        # Mark as error
        try:
            lead_list.status = 'ERROR'
            lead_list.error_message = str(e)
            lead_list.save()
        except:
            pass
        
        return {
            'success': False,
            'message': str(e)
        }

def collect_followers_with_subprocess(username: str, twitter_account: TwitterAccount, lead_list: LeadList, verbose: bool = True) -> List[Dict]:
    """
    Collect followers using subprocess to avoid async issues
    Returns list of follower data dictionaries
    """
    import subprocess
    import tempfile
    import sys
    import os
    
    try:
        if verbose:
            print(f"      🔄 Starting subprocess collection for @{username}")
            
        # Get the current cursor for this username
        pagination_state = lead_list.pagination_state or {}
        user_state = pagination_state.get(username, {})
        current_cursor = user_state.get('cursor')
        
        if verbose:
            print(f"      🔑 Current cursor for @{username}: {current_cursor}")
            print(f"      📊 Already collected: {user_state.get('collected', 0)} followers")
        
        # Create a temporary Python script to run twikit
        script_content = f'''
import asyncio
import json
import sys
import os
from twikit import Client

# Set UTF-8 encoding for Windows compatibility
if sys.platform == 'win32':
    os.environ['PYTHONIOENCODING'] = 'utf-8'
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

async def collect_followers():
    try:
        # Setup client
        cookies = {json.dumps(twitter_account.get_cookies_dict())}
        client = Client(cookies=cookies, language='en-US')
        
        # Get user info first
        try:
            user = await client.get_user_by_screen_name('{username}')
            if not user:
                return {{"error": "User not found or account suspended"}}
            user_followers_count = getattr(user, 'followers_count', 0)
        except Exception as e:
            return {{"error": f"Error accessing user: {{str(e)}}"}}
        
        collected = []
        CHUNK_SIZE = 1000   # fetch up to 1000 followers per run
        
        # Get the saved cursor - passed as a string
        saved_cursor = "{current_cursor}" if "{current_cursor}" and "{current_cursor}" != "None" else None
        
        if saved_cursor:
            print(f"Resuming collection from cursor: {{saved_cursor}}")
        else:
            print(f"Starting fresh collection")
        
        # Get first page - use saved cursor if available
        if saved_cursor:
            result = await client.get_latest_followers(
                screen_name='{username}',
                count=100,   # request 100 per page (max Twikit allows)
                cursor=saved_cursor
            )
        else:
            result = await client.get_latest_followers(
                screen_name='{username}',
                count=100
            )
        
        followers = list(result)
        next_cursor = result.next_cursor
        
        if not followers:
            return {{"success": True, "followers": [], "count": 0}}
        
        # Process first page
        for f in followers:
            if len(collected) >= CHUNK_SIZE:
                break
                
            # Clean and sanitize the data - handle Unicode properly
            try:
                follower_data = {{
                    'username': str(getattr(f, 'screen_name', '')).strip(),
                    'display_name': str(getattr(f, 'name', '')).strip(),
                    'bio': str(getattr(f, 'description', '')).strip(),
                    'location': str(getattr(f, 'location', '')).strip(),
                    'followers_count': int(getattr(f, 'followers_count', 0)),
                    'following_count': int(getattr(f, 'friends_count', 0)),
                    'tweet_count': int(getattr(f, 'statuses_count', 0)),
                    'profile_image_url': str(getattr(f, 'profile_image_url_https', '')).strip(),
                    'verified': bool(getattr(f, 'verified', False)),
                    'source_type': 'FOLLOWER',
                    'source_reference': '{username}',
                    'pagination_cursor': str(next_cursor) if next_cursor else None,
                    'pagination_collected': len(collected) + 1
                }}
                collected.append(follower_data)
            except Exception as e:
                # Skip problematic followers
                continue
        
        # Continue pagination if needed
        while next_cursor and len(collected) < CHUNK_SIZE:
            try:
                result = await client.get_latest_followers(
                    screen_name='{username}',
                    count=100,
                    cursor=next_cursor
                )
                
                followers = list(result)
                next_cursor = result.next_cursor
                
                if not followers:
                    break
                
                for f in followers:
                    if len(collected) >= CHUNK_SIZE:
                        break
                        
                    # Clean and sanitize the data - handle Unicode properly
                    try:
                        follower_data = {{
                            'username': str(getattr(f, 'screen_name', '')).strip(),
                            'display_name': str(getattr(f, 'name', '')).strip(),
                            'bio': str(getattr(f, 'description', '')).strip(),
                            'location': str(getattr(f, 'location', '')).strip(),
                            'followers_count': int(getattr(f, 'followers_count', 0)),
                            'following_count': int(getattr(f, 'friends_count', 0)),
                            'tweet_count': int(getattr(f, 'statuses_count', 0)),
                            'profile_image_url': str(getattr(f, 'profile_image_url_https', '')).strip(),
                            'verified': bool(getattr(f, 'verified', False)),
                            'source_type': 'FOLLOWER',
                            'source_reference': '{username}',
                            'pagination_cursor': str(next_cursor) if next_cursor else None,
                            'pagination_collected': len(collected) + 1
                        }}
                        collected.append(follower_data)
                    except Exception as e:
                        # Skip problematic followers
                        continue
                    
            except Exception as e:
                break
        
        return {{
            "success": True, 
            "followers": collected, 
            "count": len(collected), 
            "next_cursor": str(next_cursor) if next_cursor else None
        }}
        
    except Exception as e:
        return {{"error": str(e)}}

# Run the async function and output clean JSON
result = asyncio.run(collect_followers())
# Output JSON with proper encoding handling
try:
    json_output = json.dumps(result, ensure_ascii=False, separators=(',', ':'))
    print(json_output)
except UnicodeEncodeError:
    # Fallback: encode as ASCII with escaped Unicode
    json_output = json.dumps(result, ensure_ascii=True, separators=(',', ':'))
    print(json_output)
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
                encoding='utf-8',
                errors='replace',
                timeout=300  # 5 minute timeout
            )
            
            if result.returncode == 0:
                try:
                    # Clean the output and try to parse JSON
                    output = result.stdout.strip()
                    
                    # Find the JSON part (look for the last line that starts with {)
                    lines = output.split('\n')
                    json_line = None
                    for line in reversed(lines):
                        if line.strip().startswith('{'):
                            json_line = line.strip()
                            break
                    
                    if not json_line:
                        if verbose:
                            print(f"      ❌ No JSON found in output: {output[:200]}...")
                        return []
                    
                    data = json.loads(json_line)
                    if data.get('success'):
                        followers = data.get('followers', [])
                        next_cursor = data.get('next_cursor')
                        
                        if verbose:
                            print(f"      ✅ Collected {len(followers)} followers from @{username}")
                            print(f"      🔑 Next cursor: {next_cursor}")
                        
                        return followers
                    else:
                        error_msg = data.get('error', 'Unknown error')
                        if verbose:
                            print(f"      ❌ Error: {error_msg}")
                        return []
                except json.JSONDecodeError as e:
                    if verbose:
                        print(f"      ❌ JSON parse error: {str(e)}")
                        print(f"      ❌ Raw output: {result.stdout[:500]}...")
                    return []
            else:
                error_msg = result.stderr or "Unknown subprocess error"
                if verbose:
                    print(f"      ❌ Script failed: {error_msg}")
                return []
                    
        finally:
            # Clean up temporary file
            try:
                os.unlink(script_path)
            except:
                pass
                
    except Exception as e:
        if verbose:
            print(f"      ❌ Error in subprocess collection: {str(e)}")
        return []

def _save_followers_batch(lead_list: LeadList, followers_data: List[Dict], verbose: bool = True) -> int:
    """Save all followers to database in a batch - synchronous function"""
    saved_count = 0
    duplicate_count = 0
    
    if verbose:
        print(f"         💾 Starting batch save of {len(followers_data)} followers...")
    
    for i, follower_data in enumerate(followers_data):
        try:
            # Check if already exists
            if Lead.objects.filter(lead_list=lead_list, username=follower_data['username']).exists():
                duplicate_count += 1
                if verbose and duplicate_count <= 3:
                    print(f"         🔄 Duplicate found: @{follower_data['username']}")
                continue
            
            # Remove pagination fields before saving
            save_data = {k: v for k, v in follower_data.items() 
                       if k not in ['pagination_cursor', 'pagination_collected']}
            
            # Save lead
            lead = Lead.objects.create(
                lead_list=lead_list,
                **save_data
            )
            saved_count += 1
            
            if verbose and saved_count <= 5:
                print(f"         ✅ Saved @{follower_data['username']} (ID: {lead.id})")
            
        except Exception as e:
            if verbose:
                print(f"         ❌ Error saving @{follower_data.get('username', 'unknown')}: {str(e)}")
            continue
    
    if verbose:
        print(f"         📊 Batch save completed: {saved_count} saved, {duplicate_count} duplicates")
    
    return saved_count

def _update_pagination_state(lead_list: LeadList, followers_data: List[Dict], verbose: bool = True):
    """Update pagination state for all usernames - synchronous function"""
    try:
        pagination_state = lead_list.pagination_state or {}
        
        # Group followers by source username
        username_groups = {}
        for follower in followers_data:
            username = follower['source_reference']
            if username not in username_groups:
                username_groups[username] = []
            username_groups[username].append(follower)
        
        # Update pagination state for each username
        for username, followers in username_groups.items():
            if followers:
                last_follower = followers[-1]
                cursor = last_follower.get('pagination_cursor')
                collected = last_follower.get('pagination_collected', 0)
                
                pagination_state[username] = {
                    'cursor': cursor,
                    'collected': collected,
                    'has_more': cursor is not None,
                    'last_updated': timezone.now().isoformat()
                }
        
        lead_list.pagination_state = pagination_state
        lead_list.save(update_fields=['pagination_state'])
        
        if verbose:
            print(f"         🔄 Updated pagination state for {len(username_groups)} usernames")
            
    except Exception as e:
        if verbose:
            print(f"         ⚠️  Error updating pagination state: {str(e)}")

if __name__ == "__main__":
    # Test the collector
    print("Testing SimpleFollowerCollector...")
    # This would need to be run from Django context
    pass
