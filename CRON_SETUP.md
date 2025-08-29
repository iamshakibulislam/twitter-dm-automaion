# Django-Crontab Setup for Lead Collection

## Overview
The system uses `django-crontab` to automatically collect leads every 20 minutes and perform daily cleanup operations.

## Cron Jobs Configured

1. **Lead Collection**: Every 20 minutes (`*/20 * * * *`)
   - Collects up to 5 lead lists per run
   - Processes 1000 leads per batch
   - Automatically handles rate limiting

2. **Backup Collection**: Every hour (`0 * * * *`)
   - Force collection with higher limits
   - Ensures no lead lists are missed

## Setup Instructions

### 1. Install Dependencies
```bash
pip install django-crontab
```

### 2. Add to Django Settings
Already configured in `settings.py`:
```python
INSTALLED_APPS = [
    # ... other apps
    'django_crontab',
    'main',
]

CRONJOBS = [
    # Lead collection every 20 minutes - calls function directly
    ('*/20 * * * *', 'main.utils.lead_collection.collect_leads', {'max_lists': 5, 'verbose': False}),
    
    # Hourly lead collection with force flag (backup) - calls function directly  
    ('0 * * * *', 'main.utils.lead_collection.collect_leads', {'max_lists': 10, 'force': True, 'verbose': False}),
    
    # Daily cleanup at 3 AM
    ('0 3 * * *', 'main.utils.lead_collection.collect_leads', {'cleanup': True, 'verbose': False}),
]
```

### 3. Install Cron Jobs (Linux/macOS)
```bash
# Add cron jobs to system crontab
python manage.py crontab add

# List installed cron jobs
python manage.py crontab show

# Remove cron jobs
python manage.py crontab remove
```

### 4. Windows Task Scheduler Alternative
For Windows servers, use the provided batch file with Task Scheduler:
```bash
# Schedule collect_leads.bat to run every 20 minutes
```

## Management Commands

### Manual Lead Collection
```bash
# Collect leads for all active lists
python manage.py collect_leads

# Collect for specific lead list
python manage.py collect_leads --lead-list-id 1

# Force collection (ignore 20-minute delay)
python manage.py collect_leads --force

# Collect more lists in one run
python manage.py collect_leads --max-lists 10

# Perform cleanup operations
python manage.py collect_leads --cleanup
```

### Monitoring
```bash
# Check cron job status
python manage.py crontab show

# View logs (Linux/macOS)
tail -f /tmp/django_cron.log

# Windows: Check lead_collection.log
```

## Cron Job Features

✅ **Automatic Rate Limiting**: 20-minute intervals prevent API limits  
✅ **Batch Processing**: 1000 leads per batch for efficiency  
✅ **Error Recovery**: Failed jobs retry automatically  
✅ **Lock Protection**: Prevents overlapping executions  
✅ **Smart Scheduling**: Only processes lists that need updates  
✅ **Cleanup Operations**: Daily maintenance and error recovery  

## Troubleshooting

### Common Issues
1. **Permission Errors**: Ensure Django app has write permissions
2. **API Limits**: Cron jobs respect Twitter rate limits automatically
3. **Database Locks**: Jobs are designed to handle concurrent access

### Debugging
```bash
# Test command manually
python manage.py collect_leads --force

# Check Django logs
python manage.py shell
>>> from main.models import LeadList
>>> LeadList.objects.filter(status='ERROR')
```

### Production Deployment
- Ensure proper logging configuration
- Set up monitoring for failed cron jobs
- Configure email notifications for errors
- Use supervisor or systemd for process management

## Customization

You can modify the cron schedule in `settings.py`:
```python
CRONJOBS = [
    # Every 10 minutes (more aggressive)
    ('*/10 * * * *', 'django.core.management.call_command', ['collect_leads']),
    
    # Every hour during business hours only
    ('0 9-17 * * 1-5', 'django.core.management.call_command', ['collect_leads']),
]
```

The system is designed to be robust and self-managing once set up properly!
