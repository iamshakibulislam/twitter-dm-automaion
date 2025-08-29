# Django Shell Examples for Lead Collection

## 🚀 **Quick Start Guide**

### **1. Basic Collection (Auto-discover active lists)**
```python
python manage.py shell

# Use the synchronous version (recommended - no async errors)
from main.utils.lead_collection_sync import collect_leads

# Collect from all active lead lists
result = collect_leads()
print(result)
```

### **2. Specific Lead Lists**
```python
from main.utils.lead_collection import collect_leads

# Collect from specific lead lists
result = collect_leads(lead_list_ids=[1, 2, 3])
print(result)
```

### **3. Force Collection (Ignore 20-minute timer)**
```python
from main.utils.lead_collection import collect_leads

# Force immediate collection
result = collect_leads(force=True)
print(result)
```

### **4. Silent Mode (No console output)**
```python
from main.utils.lead_collection import collect_leads

# Run silently, just return results
result = collect_leads(verbose=False)
print(result)
```

### **5. System Stats**
```python
from main.utils.lead_collection import get_stats

# Get system overview
stats = get_stats()
```

### **6. Cleanup Operations**
```python
from main.utils.lead_collection import collect_leads

# Perform cleanup
result = collect_leads(cleanup=True)
print(result)
```

## 📊 **Expected Output Examples**

### **Successful Collection:**
```
🚀 Starting lead collection at 2025-08-29 14:35:54.909140+00:00
🎯 Selected 2 lead list(s) for processing:
   ⏳ AI Influencers (ID: 1) - PENDING
   🔄 Tech Leaders (ID: 2) - COLLECTING
⚙️  Processing 2 lead list(s)...

📊 Collection Results Summary:
==================================================
✅ Lead List 1: Collected 245 new leads (processed 1000)
   📊 Total leads: 1245, Status: COLLECTING, Account: @your_account
✅ Lead List 2: Collected 156 new leads (processed 800)
   📊 Total leads: 856, Status: COLLECTING, Account: @your_account2
==================================================
🎯 Overall: 2/2 lists processed successfully
📈 Total: 401 new leads collected (1800 profiles processed)
```

### **Return Value:**
```python
{
    'success': True,
    'action': 'auto_discovery',
    'processed_lists': [1, 2],
    'results': [
        {
            'lead_list_id': 1,
            'result': {
                'success': True,
                'collected': 245,
                'processed': 1000,
                'total_leads': 1245,
                'status': 'COLLECTING',
                'account_used': 'your_account'
            }
        },
        {
            'lead_list_id': 2,
            'result': {
                'success': True,
                'collected': 156,
                'processed': 800,
                'total_leads': 856,
                'status': 'COLLECTING',
                'account_used': 'your_account2'
            }
        }
    ],
    'processed_count': 2
}
```

## 🛠️ **Advanced Usage**

### **Test Single Lead List:**
```python
from main.utils.lead_collection import collect_leads

# Test a specific lead list with force and verbose output
result = collect_leads(
    lead_list_ids=[1], 
    force=True, 
    verbose=True
)

if result['success']:
    print("Collection successful!")
    for res in result['results']:
        print(f"Collected {res['result']['collected']} leads")
else:
    print(f"Error: {result['error']}")
```

### **Batch Processing:**
```python
from main.utils.lead_collection import collect_leads

# Process up to 10 lead lists
result = collect_leads(max_lists=10, force=True)
```

### **Error Handling:**
```python
from main.utils.lead_collection import collect_leads

try:
    result = collect_leads()
    if result['success']:
        print(f"Processed {result.get('processed_count', 0)} lead lists")
    else:
        print(f"Collection failed: {result['error']}")
except Exception as e:
    print(f"Unexpected error: {e}")
```

### **Monitor System Health:**
```python
from main.utils.lead_collection import get_stats

# Get current system status
stats = get_stats()

# Check if system is healthy
if stats['error_lead_lists'] > 0:
    print(f"⚠️  {stats['error_lead_lists']} lead lists have errors")
    
    # Run cleanup to fix errors
    from main.utils.lead_collection import collect_leads
    cleanup_result = collect_leads(cleanup=True)
    print("Cleanup completed:", cleanup_result)
```

## 🔧 **Integration Examples**

### **Custom Script:**
```python
# custom_lead_script.py
import os
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'xoutreacher.settings')
django.setup()

from main.utils.lead_collection import collect_leads, get_stats

def main():
    print("Starting custom lead collection...")
    
    # Get system stats first
    stats = get_stats()
    
    # Run collection
    result = collect_leads(max_lists=5, force=True)
    
    if result['success']:
        print(f"Successfully processed {result.get('processed_count', 0)} lists")
        return True
    else:
        print(f"Collection failed: {result['error']}")
        return False

if __name__ == "__main__":
    main()
```

### **Monitoring Script:**
```python
# monitor_leads.py
from main.utils.lead_collection import get_stats, collect_leads

def check_system_health():
    stats = get_stats()
    
    # Alert if too many errors
    if stats['error_lead_lists'] > 5:
        print("🚨 Too many lead lists in error state!")
        # Auto-cleanup
        collect_leads(cleanup=True)
    
    # Alert if no recent activity
    if stats['recent_activity'] == 0:
        print("⚠️  No recent lead collection activity")
        # Force a collection run
        collect_leads(force=True, max_lists=3)
    
    return stats

# Run health check
check_system_health()
```

## 🎯 **Key Benefits**

✅ **No Django Command Styling** - Clean, simple functions  
✅ **Direct Return Values** - Easy to parse programmatically  
✅ **Flexible Parameters** - Control every aspect of collection  
✅ **Exception Handling** - Robust error management  
✅ **Verbose Control** - Silent or detailed output  
✅ **Easy Testing** - Perfect for Django shell testing  
✅ **No Async Errors** - Synchronous version avoids all async context issues  

## ⚠️ **Important Note**

**Use `main.utils.lead_collection_sync` instead of `main.utils.lead_collection`** to avoid the async error:
```
Error collecting leads: You cannot call this from an async context - use a thread or sync_to_async.
```

**✅ FIXED!** The synchronous version now:
- **Actually collects real leads** using the `twikit` module
- **Uses subprocess** to avoid async context issues  
- **Applies all filters** (follower count, location, bio keywords)
- **Saves leads to database** with proper uniqueness checks
- **Works in cron jobs** without any async errors

The synchronous version provides the same functionality without async complications! 🚀
