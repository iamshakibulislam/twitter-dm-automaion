#!/usr/bin/env python3
"""
Debug script for save_followers_to_db function
"""

import os
import sys
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'xoutreacher.settings')
django.setup()

from main.models import Lead, LeadList
from main.utils.lead_collection_sync import save_followers_to_db, matches_filters_sync

def debug_save_function():
    """Debug the save_followers_to_db function"""
    try:
        # Get the lead list
        ll = LeadList.objects.get(id=8)
        print(f"Lead List: {ll.name}")
        print(f"Current total collected: {ll.total_collected}")
        
        # Create sample follower data similar to what comes from twikit
        sample_followers = [
            {
                'username': 'test_user_1',
                'display_name': 'Test User 1',
                'bio': 'Test bio 1',
                'location': 'Test location 1',
                'followers_count': 100,
                'following_count': 50,
                'tweet_count': 25,
                'profile_image_url': '',
                'verified': False
            },
            {
                'username': 'test_user_2',
                'display_name': 'Test User 2',
                'bio': 'Test bio 2',
                'location': 'Test location 2',
                'followers_count': 200,
                'following_count': 100,
                'tweet_count': 50,
                'profile_image_url': '',
                'verified': False
            }
        ]
        
        print(f"\nTesting with {len(sample_followers)} sample followers...")
        
        # Test filtering for each follower
        for i, follower in enumerate(sample_followers):
            matches = matches_filters_sync(follower, ll)
            print(f"Follower {i+1} (@{follower['username']}) matches filters: {matches}")
            if matches:
                print(f"  - Followers count: {follower['followers_count']}")
                print(f"  - Location: {follower['location']}")
                print(f"  - Bio: {follower['bio']}")
        
        # Test saving
        print(f"\nAttempting to save {len(sample_followers)} followers...")
        saved_count = save_followers_to_db(ll, sample_followers, 'test_source', verbose=True)
        print(f"Saved {saved_count} leads")
        
        # Check if leads were actually saved
        actual_leads = Lead.objects.filter(lead_list=ll).count()
        print(f"Actual leads in database: {actual_leads}")
        
        # Clean up test data
        Lead.objects.filter(lead_list=ll, username__startswith='test_user_').delete()
        print("Cleaned up test data")
        
        return True
        
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    debug_save_function()
