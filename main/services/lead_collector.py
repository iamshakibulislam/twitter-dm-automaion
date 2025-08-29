"""
Lead Collection Service using Twikit with Multithreading Support
Handles background collection of Twitter followers and commenters for multiple users
"""
import asyncio
import threading
import logging
from typing import List, Dict, Any, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
from django.utils import timezone
from django.db import transaction, connection
from django.contrib.auth.models import User
from ..models import LeadList, Lead, TwitterAccount
import re
import time
import random

logger = logging.getLogger(__name__)

class LeadCollector:
    """Multithreaded service for collecting leads from Twitter using twikit"""
    
    def __init__(self):
        from django.conf import settings
        
        # Load settings from Django configuration
        collection_settings = getattr(settings, 'LEAD_COLLECTION_SETTINGS', {})
        
        self.batch_size = collection_settings.get('BATCH_SIZE', 1000)
        self.max_retries = collection_settings.get('MAX_RETRIES', 3)
        self.max_threads = collection_settings.get('MAX_THREADS', 5)
        self.max_accounts_per_user = collection_settings.get('MAX_ACCOUNTS_PER_USER', 3)
        self.rate_limit_delay = collection_settings.get('RATE_LIMIT_DELAY', 30)
        self.account_timeout_minutes = collection_settings.get('ACCOUNT_TIMEOUT_MINUTES', 30)
        self.api_delay_range = collection_settings.get('API_DELAY_RANGE', (0.5, 1.5))
        
        self.account_rotation_lock = threading.Lock()
        self.active_accounts = {}  # Track active account usage
    
    def collect_leads_batch(self, lead_list_ids: List[int], max_concurrent: int = None) -> List[Dict[str, Any]]:
        """
        Collect leads for multiple lead lists concurrently using multithreading
        """
        if max_concurrent is None:
            max_concurrent = min(self.max_threads, len(lead_list_ids))
        
        results = []
        
        # Group lead lists by user to optimize account usage
        user_lead_lists = self._group_lead_lists_by_user(lead_list_ids)
        
        with ThreadPoolExecutor(max_workers=max_concurrent) as executor:
            # Submit tasks for each user's lead lists
            future_to_user = {}
            
            for user_id, user_lead_list_ids in user_lead_lists.items():
                future = executor.submit(self._collect_for_user_lead_lists, user_id, user_lead_list_ids)
                future_to_user[future] = user_id
            
            # Collect results as they complete
            for future in as_completed(future_to_user):
                user_id = future_to_user[future]
                try:
                    user_results = future.result()
                    results.extend(user_results)
                    logger.info(f"Completed lead collection for user {user_id}")
                except Exception as e:
                    logger.error(f"Error in thread for user {user_id}: {str(e)}")
                    # Add error results for this user's lead lists
                    for lead_list_id in user_lead_lists[user_id]:
                        results.append({
                            'lead_list_id': lead_list_id,
                            'success': False,
                            'message': f'Thread error: {str(e)}'
                        })
        
        return results
    
    def _group_lead_lists_by_user(self, lead_list_ids: List[int]) -> Dict[int, List[int]]:
        """Group lead lists by user for efficient account utilization"""
        user_groups = {}
        
        # Close any existing database connections to prevent thread issues
        connection.close()
        
        lead_lists = LeadList.objects.filter(id__in=lead_list_ids).select_related('user')
        
        for lead_list in lead_lists:
            user_id = lead_list.user.id
            if user_id not in user_groups:
                user_groups[user_id] = []
            user_groups[user_id].append(lead_list.id)
        
        return user_groups
    
    def _collect_for_user_lead_lists(self, user_id: int, lead_list_ids: List[int]) -> List[Dict[str, Any]]:
        """Collect leads for all lead lists belonging to a specific user"""
        # Close database connection at start of thread
        connection.close()
        
        results = []
        user = User.objects.get(id=user_id)
        
        # Get available Twitter accounts for this user
        twitter_accounts = self._get_available_twitter_accounts(user)
        
        if not twitter_accounts:
            # No accounts available, mark all as error
            for lead_list_id in lead_list_ids:
                results.append({
                    'lead_list_id': lead_list_id,
                    'success': False,
                    'message': 'No verified Twitter accounts available'
                })
            return results
        
        # Process lead lists with account rotation
        account_index = 0
        
        for lead_list_id in lead_list_ids:
            try:
                # Rotate through available accounts
                twitter_account = twitter_accounts[account_index % len(twitter_accounts)]
                account_index += 1
                
                # Mark account as in use
                with self.account_rotation_lock:
                    self.active_accounts[twitter_account.id] = timezone.now()
                
                try:
                    # Process this lead list using a new event loop for the thread
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    try:
                        # Create a synchronous wrapper for the async method
                        def run_collection():
                            return loop.run_until_complete(
                                self._collect_leads_for_list_with_account(lead_list_id, twitter_account)
                            )
                        
                        result = run_collection()
                        results.append({
                            'lead_list_id': lead_list_id,
                            **result
                        })
                    finally:
                        loop.close()
                finally:
                    # Release account
                    with self.account_rotation_lock:
                        if twitter_account.id in self.active_accounts:
                            del self.active_accounts[twitter_account.id]
                
                # Add small delay between lists to prevent rate limiting
                time.sleep(random.uniform(1, 3))
                
            except Exception as e:
                logger.error(f"Error processing lead list {lead_list_id}: {str(e)}")
                results.append({
                    'lead_list_id': lead_list_id,
                    'success': False,
                    'message': str(e)
                })
        
        return results
    
    async def _collect_leads_for_list_with_account(self, lead_list_id: int, twitter_account: TwitterAccount) -> Dict[str, Any]:
        """
        Collect leads for a specific lead list using a specific Twitter account
        """
        try:
            lead_list = LeadList.objects.get(id=lead_list_id)
            
            # Check if we can collect more leads
            if not lead_list.can_collect_more():
                return {
                    'success': False,
                    'message': 'Lead list has reached maximum capacity or is not active'
                }
            
            # Update status to collecting
            with transaction.atomic():
                lead_list.status = 'COLLECTING'
                lead_list.last_processed_at = timezone.now()
                lead_list.save()
            
            collected_count = 0
            total_processed = 0
            
            # Initialize twikit client
            client = await self._get_twitter_client(twitter_account)
            if not client:
                with transaction.atomic():
                    lead_list.status = 'ERROR'
                    lead_list.error_message = f'Failed to connect with account @{twitter_account.username}'
                    lead_list.save()
                return {
                    'success': False,
                    'message': 'Failed to connect to Twitter'
                }
            
            try:
                # Collect from followers
                if lead_list.target_usernames:
                    follower_results = await self._collect_from_followers(
                        client, lead_list, lead_list.target_usernames, twitter_account
                    )
                    collected_count += follower_results['collected']
                    total_processed += follower_results['processed']
                
                # Collect from commenters
                if lead_list.target_post_urls:
                    commenter_results = await self._collect_from_commenters(
                        client, lead_list, lead_list.target_post_urls, twitter_account
                    )
                    collected_count += commenter_results['collected']
                    total_processed += commenter_results['processed']
                
            except Exception as collection_error:
                # Handle rate limiting gracefully
                if "rate limit" in str(collection_error).lower():
                    logger.warning(f"Rate limit hit for account @{twitter_account.username}, will retry later")
                    return {
                        'success': False,
                        'message': f'Rate limit reached for @{twitter_account.username}',
                        'retry_after': self.rate_limit_delay
                    }
                else:
                    raise collection_error
            
            # Update lead list stats
            with transaction.atomic():
                lead_list.refresh_from_db()
                lead_list.total_collected = Lead.objects.filter(lead_list=lead_list).count()
                
                # Check if collection is complete
                if lead_list.total_collected >= lead_list.max_leads:
                    lead_list.status = 'COMPLETED'
                elif collected_count == 0 and total_processed > 0:
                    lead_list.status = 'PAUSED'
                else:
                    lead_list.status = 'COLLECTING'
                
                lead_list.last_processed_at = timezone.now()
                lead_list.save()
            
            return {
                'success': True,
                'collected': collected_count,
                'processed': total_processed,
                'total_leads': lead_list.total_collected,
                'status': lead_list.status,
                'account_used': twitter_account.username
            }
            
        except Exception as e:
            logger.error(f"Error collecting leads for list {lead_list_id}: {str(e)}")
            try:
                with transaction.atomic():
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
    
    async def collect_leads_for_list(self, lead_list_id: int) -> Dict[str, Any]:
        """
        Legacy method for single lead list collection (for backwards compatibility)
        """
        results = self.collect_leads_batch([lead_list_id], max_concurrent=1)
        if results:
            result = results[0]
            # Remove lead_list_id from result for compatibility
            result.pop('lead_list_id', None)
            return result
        else:
            return {
                'success': False,
                'message': 'No results returned from batch collection'
            }
    
    async def _collect_from_followers(self, client, lead_list: LeadList, usernames: List[str], twitter_account: TwitterAccount) -> Dict[str, int]:
        """Collect leads from user followers with proper pagination tracking"""
        collected = 0
        processed = 0
        
        # Get or initialize pagination state
        pagination_state = lead_list.pagination_state or {}
        
        for username in usernames:
            try:
                # Get user object
                user = await client.get_user_by_screen_name(username)
                if not user:
                    logger.warning(f"User not found: {username}")
                    continue
                
                logger.info(f"Collecting followers for @{username} using @{twitter_account.username}")
                
                # Check if we have existing pagination state for this username
                pagination_key = f"followers_{username}"
                
                # Get followers with proper pagination like the sample code
                followers_result = None
                followers_collected_this_user = 0
                
                if pagination_key in pagination_state and not pagination_state[pagination_key].get('completed', False):
                    # Resume from saved pagination state
                    saved_state = pagination_state[pagination_key]
                    logger.info(f"Resuming pagination for @{username} from saved state (collected: {saved_state.get('collected_count', 0)})")
                    
                    # For twikit, we need to start fresh but skip already collected leads
                    # The uniqueness check in the collection loop will handle duplicates
                    followers_result = await user.get_followers(count=min(200, self.batch_size))
                else:
                    # First time collecting from this user or completed previous collection
                    if pagination_key in pagination_state and pagination_state[pagination_key].get('completed', False):
                        logger.info(f"@{username} collection already completed, skipping")
                        continue
                    
                    logger.info(f"Starting fresh collection for @{username}")
                    followers_result = await user.get_followers(count=min(200, self.batch_size))
                
                # Collect followers with pagination
                while followers_result and followers_collected_this_user < self.batch_size and collected < self.batch_size:
                    for follower in followers_result:
                        processed += 1
                        
                        # Check if we've reached the batch limit
                        if collected >= self.batch_size or followers_collected_this_user >= self.batch_size:
                            break
                        
                        # Check for uniqueness - if lead already exists, skip
                        # Using select_related for performance with the new index
                        if Lead.objects.filter(lead_list=lead_list, username=follower.screen_name).exists():
                            continue
                        
                        # Apply filters
                        if self._matches_filters(follower, lead_list):
                            lead_data = self._extract_lead_data(follower, 'FOLLOWER', username)
                            if self._save_lead(lead_list, lead_data):
                                collected += 1
                                followers_collected_this_user += 1
                                logger.debug(f"Collected lead: @{follower.screen_name} from @{username}")
                    
                    # Break if we've collected enough for this batch
                    if collected >= self.batch_size or followers_collected_this_user >= self.batch_size:
                        break
                    
                    # Get next page using the proper pagination method like sample code
                    try:
                        logger.info(f"Getting next page for @{username}...")
                        followers_result = await followers_result.next()
                        
                        # Add small delay between pages to respect rate limits
                        await asyncio.sleep(random.uniform(*self.api_delay_range))
                        
                    except Exception as pagination_error:
                        logger.info(f"No more pages for @{username}: {str(pagination_error)}")
                        break
                
                # Save pagination state for this username
                pagination_state[pagination_key] = {
                    'completed': followers_collected_this_user >= self.batch_size,
                    'last_processed': timezone.now().isoformat(),
                    'collected_count': followers_collected_this_user
                }
                
                logger.info(f"Collected {followers_collected_this_user} followers from @{username}")
                
                # Break if we've collected enough for this batch
                if collected >= self.batch_size:
                    break
                
                # Add delay between different users
                await asyncio.sleep(random.uniform(*self.api_delay_range))
                    
            except Exception as e:
                logger.error(f"Error collecting followers for {username} using @{twitter_account.username}: {str(e)}")
                # If rate limited, wait and continue with next username
                if "rate limit" in str(e).lower():
                    logger.warning(f"Rate limit hit, waiting {self.rate_limit_delay} seconds")
                    await asyncio.sleep(self.rate_limit_delay)
                continue
        
        # Save updated pagination state
        lead_list.pagination_state = pagination_state
        lead_list.save(update_fields=['pagination_state'])
        
        return {'collected': collected, 'processed': processed}
    
    async def _collect_from_commenters(self, client, lead_list: LeadList, post_urls: List[str], twitter_account: TwitterAccount) -> Dict[str, int]:
        """Collect leads from post commenters with proper pagination tracking"""
        collected = 0
        processed = 0
        
        # Get or initialize pagination state
        pagination_state = lead_list.pagination_state or {}
        
        for post_url in post_urls:
            try:
                # Extract tweet ID from URL
                tweet_id = self._extract_tweet_id(post_url)
                if not tweet_id:
                    logger.warning(f"Could not extract tweet ID from URL: {post_url}")
                    continue
                
                logger.info(f"Collecting commenters for tweet {tweet_id} using @{twitter_account.username}")
                
                # Check if we have existing pagination state for this post
                pagination_key = f"commenters_{tweet_id}"
                
                # Get tweet comments with proper pagination
                comments_result = None
                commenters_collected_this_post = 0
                
                if pagination_key in pagination_state and not pagination_state[pagination_key].get('completed', False):
                    # Resume from saved pagination state
                    saved_state = pagination_state[pagination_key]
                    logger.info(f"Resuming pagination for tweet {tweet_id} from saved state (collected: {saved_state.get('collected_count', 0)})")
                    
                    # For twikit, we need to start fresh but skip already collected leads
                    # The uniqueness check in the collection loop will handle duplicates
                    comments_result = await client.get_tweet_comments(tweet_id, count=min(200, self.batch_size))
                else:
                    # First time collecting from this post or completed previous collection
                    if pagination_key in pagination_state and pagination_state[pagination_key].get('completed', False):
                        logger.info(f"Tweet {tweet_id} collection already completed, skipping")
                        continue
                    
                    logger.info(f"Starting fresh collection for tweet {tweet_id}")
                    comments_result = await client.get_tweet_comments(tweet_id, count=min(200, self.batch_size))
                
                # Collect commenters with pagination
                while comments_result and commenters_collected_this_post < self.batch_size and collected < self.batch_size:
                    for comment in comments_result:
                        processed += 1
                        
                        # Check if we've reached the batch limit
                        if collected >= self.batch_size or commenters_collected_this_post >= self.batch_size:
                            break
                        
                        # Check for uniqueness - if lead already exists, skip
                        # Using select_related for performance with the new index
                        if Lead.objects.filter(lead_list=lead_list, username=comment.user.screen_name).exists():
                            continue
                        
                        # Apply filters
                        if self._matches_filters(comment.user, lead_list):
                            lead_data = self._extract_lead_data(comment.user, 'COMMENTER', post_url)
                            if self._save_lead(lead_list, lead_data):
                                collected += 1
                                commenters_collected_this_post += 1
                                logger.debug(f"Collected lead: @{comment.user.screen_name} from tweet {tweet_id}")
                    
                    # Break if we've collected enough for this batch
                    if collected >= self.batch_size or commenters_collected_this_post >= self.batch_size:
                        break
                    
                    # Get next page using the proper pagination method
                    try:
                        logger.info(f"Getting next page for tweet {tweet_id}...")
                        comments_result = await comments_result.next()
                        
                        # Add small delay between pages to respect rate limits
                        await asyncio.sleep(random.uniform(*self.api_delay_range))
                        
                    except Exception as pagination_error:
                        logger.info(f"No more pages for tweet {tweet_id}: {str(pagination_error)}")
                        break
                
                # Save pagination state for this post
                pagination_state[pagination_key] = {
                    'completed': commenters_collected_this_post >= self.batch_size,
                    'last_processed': timezone.now().isoformat(),
                    'collected_count': commenters_collected_this_post
                }
                
                logger.info(f"Collected {commenters_collected_this_post} commenters from tweet {tweet_id}")
                
                # Break if we've collected enough for this batch
                if collected >= self.batch_size:
                    break
                
                # Add delay between different posts
                await asyncio.sleep(random.uniform(*self.api_delay_range))
                    
            except Exception as e:
                logger.error(f"Error collecting commenters for {post_url} using @{twitter_account.username}: {str(e)}")
                # If rate limited, wait and continue with next post
                if "rate limit" in str(e).lower():
                    logger.warning(f"Rate limit hit, waiting {self.rate_limit_delay} seconds")
                    await asyncio.sleep(self.rate_limit_delay)
                continue
        
        # Save updated pagination state
        lead_list.pagination_state = pagination_state
        lead_list.save(update_fields=['pagination_state'])
        
        return {'collected': collected, 'processed': processed}
    
    def _matches_filters(self, user, lead_list: LeadList) -> bool:
        """Check if user matches the lead list filters"""
        try:
            # Follower count filter
            follower_count = getattr(user, 'followers_count', 0)
            if follower_count < lead_list.min_followers or follower_count > lead_list.max_followers:
                return False
            
            # Location filter (if specified, user must match)
            if lead_list.locations:
                user_location = getattr(user, 'location', '') or ''
                location_match = any(
                    location.lower() in user_location.lower() 
                    for location in lead_list.locations
                )
                if not location_match:
                    return False
            
            # Bio keyword filters
            user_bio = getattr(user, 'description', '') or ''
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
    
    def _extract_lead_data(self, user, source_type: str, source_reference: str) -> Dict[str, Any]:
        """Extract lead data from Twitter user object"""
        return {
            'username': getattr(user, 'screen_name', ''),
            'display_name': getattr(user, 'name', ''),
            'bio': getattr(user, 'description', ''),
            'location': getattr(user, 'location', ''),
            'followers_count': getattr(user, 'followers_count', 0),
            'following_count': getattr(user, 'friends_count', 0),
            'tweet_count': getattr(user, 'statuses_count', 0),
            'profile_image_url': getattr(user, 'profile_image_url_https', ''),
            'verified': getattr(user, 'verified', False),
            'source_type': source_type,
            'source_reference': source_reference,
        }
    
    def _save_lead(self, lead_list: LeadList, lead_data: Dict[str, Any]) -> bool:
        """Save lead to database"""
        try:
            with transaction.atomic():
                lead, created = Lead.objects.get_or_create(
                    lead_list=lead_list,
                    username=lead_data['username'],
                    defaults=lead_data
                )
                return created
        except Exception as e:
            logger.error(f"Error saving lead {lead_data.get('username')}: {str(e)}")
            return False
    
    def _get_verified_twitter_account(self, user) -> Optional[TwitterAccount]:
        """Get a verified Twitter account for the user (legacy method)"""
        return TwitterAccount.objects.filter(
            user=user,
            is_verified=True,
            is_active=True
        ).first()
    
    def _get_available_twitter_accounts(self, user) -> List[TwitterAccount]:
        """Get all available verified Twitter accounts for the user"""
        accounts = list(TwitterAccount.objects.filter(
            user=user,
            is_verified=True,
            is_active=True
        ).order_by('-last_verified'))
        
        # Filter out accounts that are currently in use
        with self.account_rotation_lock:
            available_accounts = []
            for account in accounts:
                # Check if account is not currently being used
                if account.id not in self.active_accounts:
                    available_accounts.append(account)
                else:
                    # Check if account has been in use for too long (stuck)
                    last_used = self.active_accounts[account.id]
                    if timezone.now() - last_used > timezone.timedelta(minutes=self.account_timeout_minutes):
                        # Release stuck account
                        del self.active_accounts[account.id]
                        available_accounts.append(account)
            
            # If no accounts available, return the least recently used ones
            if not available_accounts and accounts:
                logger.warning(f"All accounts for user {user.id} are in use, using least recently used")
                available_accounts = accounts[:self.max_accounts_per_user]
        
        return available_accounts
    
    async def _get_twitter_client(self, twitter_account: TwitterAccount):
        """Initialize Twitter client with account credentials"""
        try:
            from twikit import Client
            
            cookies = twitter_account.get_cookies_dict()
            client = Client(cookies=cookies, language='en-US')
            
            # Test the connection
            test_user = await client.user()
            if test_user:
                return client
            else:
                return None
                
        except Exception as e:
            logger.error(f"Error initializing Twitter client: {str(e)}")
            return None
    
    def _extract_tweet_id(self, post_url: str) -> Optional[str]:
        """Extract tweet ID from Twitter URL"""
        pattern = r'https?://(twitter\.com|x\.com)/.+/status/(\d+)'
        match = re.search(pattern, post_url)
        return match.group(2) if match else None

# Global instance
lead_collector = LeadCollector()
