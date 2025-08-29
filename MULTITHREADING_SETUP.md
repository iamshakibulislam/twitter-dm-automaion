# Multithreading Setup for Lead Collection

## Overview
The Lead Collection system now supports **full multithreading** for handling multiple users and multiple Twitter accounts simultaneously. This ensures optimal performance and resource utilization for large-scale operations.

## 🚀 **Key Features**

### **Multi-User Support**
- ✅ **Concurrent Users**: Process multiple users' lead lists simultaneously
- ✅ **User Isolation**: Each user's collection runs in separate threads
- ✅ **Account Rotation**: Automatically rotates through available Twitter accounts per user

### **Multi-Account Management**
- ✅ **Account Pooling**: Uses all verified Twitter accounts for each user
- ✅ **Smart Rotation**: Prevents rate limiting by rotating accounts
- ✅ **Thread Safety**: Thread-safe account locking prevents conflicts
- ✅ **Stuck Account Recovery**: Automatically releases stuck accounts after timeout

### **Performance Optimization**
- ✅ **ThreadPoolExecutor**: Efficient thread management
- ✅ **Database Optimization**: Thread-safe database connections
- ✅ **Rate Limit Handling**: Intelligent rate limit detection and recovery
- ✅ **Configurable Settings**: Easily adjustable performance parameters

## ⚙️ **Configuration Settings**

### Django Settings (`settings.py`)
```python
LEAD_COLLECTION_SETTINGS = {
    'MAX_THREADS': 5,  # Maximum concurrent threads for lead collection
    'MAX_ACCOUNTS_PER_USER': 3,  # Max Twitter accounts to use per user simultaneously
    'BATCH_SIZE': 1000,  # Leads to collect per batch
    'RATE_LIMIT_DELAY': 30,  # Seconds to wait on rate limit
    'MAX_RETRIES': 3,  # Maximum retry attempts
    'ACCOUNT_TIMEOUT_MINUTES': 30,  # Minutes before releasing stuck accounts
    'API_DELAY_RANGE': (0.5, 1.5),  # Random delay between API calls (min, max)
}
```

### Database Configuration
```python
DATABASES['default'].update({
    'CONN_MAX_AGE': 0,  # Prevent persistent connections in threads
    'OPTIONS': {
        'init_command': "SET sql_mode='STRICT_TRANS_TABLES'",
        'charset': 'utf8mb4',
    } if 'mysql' in DATABASES['default']['ENGINE'] else {}
})
```

## 🏗️ **Architecture**

### **Thread Distribution**
```
Cron Job (Every 20 minutes)
├── ThreadPoolExecutor (Max 5 threads)
│   ├── Thread 1: User A (Lead Lists 1,2,3)
│   │   ├── Twitter Account A1 → Lead List 1
│   │   ├── Twitter Account A2 → Lead List 2
│   │   └── Twitter Account A3 → Lead List 3
│   ├── Thread 2: User B (Lead Lists 4,5)
│   │   ├── Twitter Account B1 → Lead List 4
│   │   └── Twitter Account B2 → Lead List 5
│   └── Thread 3: User C (Lead Lists 6,7,8)
│       ├── Twitter Account C1 → Lead List 6
│       ├── Twitter Account C2 → Lead List 7
│       └── Twitter Account C1 → Lead List 8 (rotated)
```

### **Account Management Flow**
1. **Account Discovery**: Find all verified accounts per user
2. **Thread Assignment**: Group lead lists by user
3. **Account Rotation**: Rotate through available accounts
4. **Lock Management**: Thread-safe account usage tracking
5. **Rate Limit Handling**: Automatic delays and retries
6. **Cleanup**: Release accounts when done

## 🔧 **Key Methods**

### **Batch Collection**
```python
# Collect multiple lead lists with multithreading
results = lead_collector.collect_leads_batch(
    lead_list_ids=[1, 2, 3, 4, 5],
    max_concurrent=5
)
```

### **User Grouping**
```python
# Groups lead lists by user for efficient processing
user_groups = {
    user_1: [lead_list_1, lead_list_2],
    user_2: [lead_list_3, lead_list_4],
    user_3: [lead_list_5]
}
```

### **Account Rotation**
```python
# Automatically rotates through user's Twitter accounts
for lead_list in user_lead_lists:
    account = accounts[index % len(accounts)]
    # Process with this account
    index += 1
```

## 📊 **Performance Benefits**

### **Before (Single-threaded)**
- ❌ One lead list at a time
- ❌ One Twitter account per user
- ❌ Sequential processing
- ❌ Poor resource utilization

### **After (Multi-threaded)**
- ✅ 5+ lead lists simultaneously
- ✅ 3+ Twitter accounts per user
- ✅ Parallel processing
- ✅ Optimal resource utilization

### **Example Performance**
```
Single-threaded: 1000 leads/20min = 50 leads/min
Multi-threaded:   5000 leads/20min = 250 leads/min (5x improvement)
```

## 🛡️ **Thread Safety Features**

### **Database Connections**
- ✅ **Connection Closing**: Closes connections at thread start
- ✅ **Atomic Transactions**: Thread-safe database operations
- ✅ **Connection Pooling**: Prevents connection conflicts

### **Account Locking**
- ✅ **Mutex Locks**: Thread-safe account access
- ✅ **Usage Tracking**: Prevents account conflicts
- ✅ **Timeout Recovery**: Releases stuck accounts

### **Error Handling**
- ✅ **Exception Isolation**: Thread errors don't affect others
- ✅ **Graceful Degradation**: Continue processing on partial failures
- ✅ **Retry Logic**: Automatic retry with exponential backoff

## 🚀 **Usage Examples**

### **Manual Batch Collection**
```bash
# Process specific lead lists
python manage.py collect_leads --lead-list-id 1 --lead-list-id 2

# Force collection with higher concurrency
python manage.py collect_leads --force --max-lists 10
```

### **Monitoring Active Threads**
```python
# Check active account usage
from main.services.lead_collector import lead_collector
print(f"Active accounts: {lead_collector.active_accounts}")
```

### **Performance Tuning**
```python
# Adjust for high-traffic scenarios
LEAD_COLLECTION_SETTINGS = {
    'MAX_THREADS': 10,  # Increase for more users
    'MAX_ACCOUNTS_PER_USER': 5,  # More accounts per user
    'BATCH_SIZE': 500,  # Smaller batches for faster iteration
    'RATE_LIMIT_DELAY': 15,  # Aggressive rate limiting
}
```

## ⚠️ **Production Considerations**

### **Scaling Guidelines**
- **Small Scale**: 1-10 users → 3-5 threads
- **Medium Scale**: 10-100 users → 5-10 threads
- **Large Scale**: 100+ users → 10-20 threads

### **Resource Requirements**
- **CPU**: 1 core per 2-3 threads
- **Memory**: 200MB per active thread
- **Database**: Connection pooling essential

### **Monitoring**
- Track thread utilization
- Monitor account rotation efficiency
- Watch for rate limit patterns
- Alert on stuck threads

The multithreading system is now production-ready and can handle multiple users with multiple Twitter accounts efficiently! 🎯
