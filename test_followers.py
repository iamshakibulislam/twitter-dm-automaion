#!/usr/bin/env python3
"""
Test script for the updated followers collection system
"""

import asyncio
import json
from twikit import Client

# Test cookies (replace with your actual cookies)
cookies = {
    "auth_token": "ed6ff46c298d01e348876fc6c6e1c9f4cb2752c1",
    "ct0": "eddae2ccc1f40fdca320715e50d416886e677ae9e88b95b6b9b9b82ded9156c47dbd21d7e41076e08aa4f7394eee7857b3e8f19d9eb9975b1bb24f7d27a9a1bf5af88520af83e8e1e4bba0ffec52f4dd"
}

async def test_followers_collection():
    """Test the followers collection logic"""
    try:
        client = Client(cookies=cookies, language='en-US')
        
        # Test username
        username = "vip_cham"
        
        print(f"Testing followers collection for @{username}")
        
        # Get user info first
        try:
            user = await client.get_user_by_screen_name(username)
            if not user:
                print("User not found or account suspended")
                return
            user_followers_count = getattr(user, 'followers_count', 0)
            print(f"User @{username} has {user_followers_count} followers")
        except Exception as e:
            print(f"Error accessing user: {str(e)}")
            return
        
        # Test followers collection
        cursor = None
        collected = []
        CHUNK_SIZE = 1000   # fetch up to 1000 followers per run
        
        print(f"Starting collection with CHUNK_SIZE={CHUNK_SIZE}")
        
        new_cursor = cursor
        run_followers = []  # new ones this run
        
        # Keep paging until we hit CHUNK_SIZE
        while len(run_followers) < CHUNK_SIZE:
            if new_cursor:
                print(f"Fetching with cursor: {new_cursor}")
                result = await client.get_latest_followers(
                    screen_name=username,
                    count=100,   # request 100 per page (max Twikit allows)
                    cursor=new_cursor
                )
            else:
                print("Fetching first page")
                result = await client.get_latest_followers(
                    screen_name=username,
                    count=100
                )
            
            followers = list(result)
            new_cursor = result.next_cursor
            
            print(f"Got {len(followers)} followers, next_cursor: {new_cursor}")
            
            if not followers:
                print("No more followers available.")
                break
            
            for f in followers:
                follower_data = {
                    'username': getattr(f, 'screen_name', ''),
                    'display_name': getattr(f, 'name', ''),
                    'bio': getattr(f, 'description', ''),
                    'location': getattr(f, 'location', ''),
                    'followers_count': getattr(f, 'followers_count', 0),
                    'following_count': getattr(f, 'friends_count', 0),
                    'tweet_count': getattr(f, 'statuses_count', 0),
                    'profile_image_url': getattr(f, 'profile_image_url_https', ''),
                    'verified': getattr(f, 'verified', False),
                }
                run_followers.append(follower_data)
                
                if len(run_followers) >= CHUNK_SIZE:
                    break
            
            if not new_cursor:  # no more pages
                break
        
        # Results
        has_more = new_cursor is not None and len(run_followers) >= CHUNK_SIZE
        
        print(f"\n=== RESULTS ===")
        print(f"Fetched {len(run_followers)} followers this run")
        print(f"Total available: {user_followers_count}")
        print(f"Next cursor: {new_cursor}")
        print(f"Has more: {has_more}")
        
        # Show first few followers
        print(f"\n=== SAMPLE FOLLOWERS ===")
        for i, follower in enumerate(run_followers[:5]):
            print(f"{i+1}. @{follower['username']} - {follower['display_name']}")
            print(f"   Location: {follower['location']}")
            print(f"   Followers: {follower['followers_count']}")
            print()
        
        return {
            "success": True, 
            "followers": run_followers, 
            "count": len(run_followers), 
            "total_available": user_followers_count,
            "has_more": has_more,
            "next_cursor": new_cursor
        }
        
    except Exception as e:
        print(f"Error: {str(e)}")
        return {"error": str(e)}

if __name__ == "__main__":
    print("Testing Twikit Followers Collection")
    print("=" * 40)
    
    result = asyncio.run(test_followers_collection())
    
    if result.get('success'):
        print(f"\n✅ SUCCESS: Collected {result['count']} followers")
        print(f"Next cursor for resuming: {result['next_cursor']}")
    else:
        print(f"\n❌ FAILED: {result.get('error', 'Unknown error')}")
