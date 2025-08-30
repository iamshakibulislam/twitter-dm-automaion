#!/usr/bin/env python3
"""
Test script for lead creation
"""

import os
import sys
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'xoutreacher.settings')
django.setup()

from main.models import Lead, LeadList

def test_lead_creation():
    """Test creating a lead manually"""
    try:
        # Get the lead list
        ll = LeadList.objects.get(id=8)
        print(f"Lead List: {ll.name}")
        
        # Test creating a lead
        lead = Lead.objects.create(
            lead_list=ll,
            username='test_user_123',
            display_name='Test User 123',
            bio='Test bio',
            location='Test location',
            followers_count=100,
            following_count=50,
            tweet_count=25,
            profile_image_url='',
            verified=False,
            source_type='FOLLOWER',
            source_reference='test_source'
        )
        print(f"✅ Lead created successfully: {lead.id}")
        
        # Delete the test lead
        lead.delete()
        print("✅ Lead deleted successfully")
        
        return True
        
    except Exception as e:
        print(f"❌ Error creating lead: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_lead_creation()
    if success:
        print("🎉 Lead creation test passed!")
    else:
        print("💥 Lead creation test failed!")
