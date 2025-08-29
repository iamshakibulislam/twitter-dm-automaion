"""
Standalone lead collection utilities
Use these functions directly in Django shell or scripts
"""
import logging
from django.utils import timezone
from datetime import timedelta
from main.models import LeadList, Lead
from main.services.lead_collector import lead_collector

logger = logging.getLogger(__name__)

def collect_leads(lead_list_ids=None, max_lists=5, force=False, cleanup=False, verbose=True):
    """
    Collect leads for active lead lists
    
    Usage in Django shell:
        from main.utils.lead_collection import collect_leads
        
        # Collect from all active lists
        result = collect_leads()
        
        # Collect from specific lists
        result = collect_leads(lead_list_ids=[1, 2, 3])
        
        # Force collection
        result = collect_leads(force=True)
        
        # Silent mode
        result = collect_leads(verbose=False)
    
    Args:
        lead_list_ids (list): Specific lead list IDs to process
        max_lists (int): Maximum number of lead lists to process
        force (bool): Force collection regardless of timing restrictions
        cleanup (bool): Perform cleanup of old lead lists and error logs
        verbose (bool): Print detailed output
    
    Returns:
        dict: Results of the collection process
    """
    if verbose:
        print(f'🚀 Starting lead collection at {timezone.now()}')
    
    try:
        if cleanup:
            # Perform cleanup operations
            cleanup_result = perform_cleanup(verbose=verbose)
            return {'success': True, 'action': 'cleanup', 'result': cleanup_result}
            
        elif lead_list_ids:
            # Process specific lead lists
            if verbose:
                print(f'📋 Processing {len(lead_list_ids)} specific lead list(s): {lead_list_ids}')
            
            results = process_lead_lists_sync(lead_list_ids, force=force, verbose=verbose)
            
            if verbose:
                for result in results:
                    print_result(result)
                    
            return {
                'success': True, 
                'action': 'specific_lists',
                'processed_lists': lead_list_ids,
                'results': results
            }
            
        else:
            # Process multiple lead lists automatically
            lead_lists = get_lead_lists_for_processing(max_lists, force, verbose=verbose)
            
            if lead_lists:
                lead_list_ids = [lead_list.id for lead_list in lead_lists]
                if verbose:
                    print(f'📋 Found {len(lead_list_ids)} lead list(s) ready for processing')
                
                results = process_lead_lists_sync(lead_list_ids, force=force, verbose=verbose)
                
                if verbose:
                    print_batch_results(results)
                    
                return {
                    'success': True, 
                    'action': 'auto_discovery',
                    'processed_lists': lead_list_ids,
                    'results': results,
                    'processed_count': len(results)
                }
            else:
                if verbose:
                    print('ℹ️  No lead lists ready for processing')
                return {
                    'success': True, 
                    'action': 'auto_discovery',
                    'message': 'No lead lists ready for processing'
                }
                
    except Exception as e:
        error_msg = f'❌ Error during lead collection: {str(e)}'
        if verbose:
            print(error_msg)
        logger.error(f'Lead collection error: {str(e)}')
        return {'success': False, 'error': str(e)}


def process_lead_lists_sync(lead_list_ids, force=False, verbose=True):
    """Process lead lists synchronously using the batch collector"""
    try:
        if verbose:
            print(f'⚙️  Processing {len(lead_list_ids)} lead list(s)...')
        
        # Call the batch collection method
        batch_results = lead_collector.collect_leads_batch(
            lead_list_ids, 
            max_concurrent=min(5, len(lead_list_ids))
        )
        
        # Convert batch results to expected format
        processed_results = []
        for result in batch_results:
            lead_list_id = result.pop('lead_list_id', None)
            processed_results.append({
                'lead_list_id': lead_list_id,
                'result': result
            })
        
        return processed_results
        
    except Exception as e:
        if verbose:
            print(f'❌ Error in batch processing: {str(e)}')
        logger.error(f'Error in batch processing: {str(e)}')
        return []


def get_lead_lists_for_processing(max_lists, force=False, verbose=True):
    """Get lead lists that are ready for processing"""
    from django.db import models
    
    # Base queryset for active lead lists
    queryset = LeadList.objects.filter(
        status__in=['PENDING', 'COLLECTING', 'PAUSED']
    ).exclude(
        total_collected__gte=models.F('max_leads')
    )
    
    if not force:
        # Only process lists that haven't been processed recently (20 minutes)
        cutoff_time = timezone.now() - timedelta(minutes=20)
        queryset = queryset.filter(
            models.Q(last_processed_at__isnull=True) | 
            models.Q(last_processed_at__lt=cutoff_time)
        )
    
    # Order by priority: ERROR first (for retry), then by last processed
    lead_lists = list(queryset.order_by(
        models.Case(
            models.When(status='ERROR', then=0),
            models.When(status='PENDING', then=1),
            models.When(status='PAUSED', then=2),
            models.When(status='COLLECTING', then=3),
            default=4
        ),
        'last_processed_at'
    )[:max_lists])
    
    if verbose and lead_lists:
        print(f'🎯 Selected {len(lead_lists)} lead list(s) for processing:')
        for lead_list in lead_lists:
            status_emoji = {'PENDING': '⏳', 'COLLECTING': '🔄', 'PAUSED': '⏸️', 'ERROR': '⚠️'}.get(lead_list.status, '❓')
            print(f'   {status_emoji} {lead_list.name} (ID: {lead_list.id}) - {lead_list.status}')
    
    return lead_lists


def perform_cleanup(verbose=True):
    """Perform cleanup operations on lead lists"""
    from django.db import models
    
    if verbose:
        print('🧹 Performing cleanup operations...')
    
    cleanup_stats = {
        'error_lists_reset': 0,
        'completed_lists_marked': 0,
        'old_errors_cleared': 0
    }
    
    # Reset ERROR status for lists that failed more than 1 hour ago
    error_cutoff = timezone.now() - timedelta(hours=1)
    error_lists = LeadList.objects.filter(
        status='ERROR',
        last_processed_at__lt=error_cutoff
    )
    
    for lead_list in error_lists:
        lead_list.status = 'PENDING'
        lead_list.error_message = ''
        lead_list.save(update_fields=['status', 'error_message'])
        cleanup_stats['error_lists_reset'] += 1
        if verbose:
            print(f'   ✅ Reset error status for: {lead_list.name}')
    
    # Mark completed lists
    completed_lists = LeadList.objects.filter(
        total_collected__gte=models.F('max_leads')
    ).exclude(status='COMPLETED')
    
    for lead_list in completed_lists:
        lead_list.status = 'COMPLETED'
        lead_list.save(update_fields=['status'])
        cleanup_stats['completed_lists_marked'] += 1
        if verbose:
            print(f'   🎉 Marked as completed: {lead_list.name}')
    
    # Clear old error messages (older than 7 days)
    old_error_cutoff = timezone.now() - timedelta(days=7)
    old_error_lists = LeadList.objects.filter(
        error_message__isnull=False,
        last_processed_at__lt=old_error_cutoff
    ).exclude(error_message='')
    
    for lead_list in old_error_lists:
        lead_list.error_message = ''
        lead_list.save(update_fields=['error_message'])
        cleanup_stats['old_errors_cleared'] += 1
    
    if verbose:
        print(f'🧹 Cleanup completed: {cleanup_stats}')
    
    return cleanup_stats


def print_result(result_dict):
    """Print a single result in a formatted way"""
    lead_list_id = result_dict.get('lead_list_id')
    result = result_dict.get('result', {})
    
    if result.get('success'):
        collected = result.get('collected', 0)
        processed = result.get('processed', 0)
        total_leads = result.get('total_leads', 0)
        status = result.get('status', 'UNKNOWN')
        account_used = result.get('account_used', 'Unknown')
        
        print(f'✅ Lead List {lead_list_id}: Collected {collected} new leads (processed {processed})')
        print(f'   📊 Total leads: {total_leads}, Status: {status}, Account: @{account_used}')
    else:
        message = result.get('message', 'Unknown error')
        print(f'❌ Lead List {lead_list_id}: Failed - {message}')


def print_batch_results(results):
    """Print batch results in a formatted way"""
    print(f'\n📊 Collection Results Summary:')
    print('=' * 50)
    
    total_collected = 0
    total_processed = 0
    success_count = 0
    
    for result_dict in results:
        result = result_dict.get('result', {})
        if result.get('success'):
            success_count += 1
            total_collected += result.get('collected', 0)
            total_processed += result.get('processed', 0)
        
        print_result(result_dict)
    
    print('=' * 50)
    print(f'🎯 Overall: {success_count}/{len(results)} lists processed successfully')
    print(f'📈 Total: {total_collected} new leads collected ({total_processed} profiles processed)')


def get_stats():
    """Get quick stats about the lead collection system"""
    from django.db import models
    
    stats = {
        'total_lead_lists': LeadList.objects.count(),
        'active_lead_lists': LeadList.objects.filter(status__in=['PENDING', 'COLLECTING', 'PAUSED']).count(),
        'completed_lead_lists': LeadList.objects.filter(status='COMPLETED').count(),
        'error_lead_lists': LeadList.objects.filter(status='ERROR').count(),
        'total_leads': Lead.objects.count(),
        'recent_activity': LeadList.objects.filter(
            last_processed_at__gte=timezone.now() - timedelta(hours=24)
        ).count()
    }
    
    print('📈 Lead Collection System Stats:')
    print('=' * 40)
    for key, value in stats.items():
        emoji = {'total_lead_lists': '📋', 'active_lead_lists': '🔄', 'completed_lead_lists': '✅', 
                'error_lead_lists': '❌', 'total_leads': '👥', 'recent_activity': '⏰'}.get(key, '📊')
        print(f'{emoji} {key.replace("_", " ").title()}: {value:,}')
    
    return stats


# Import fix for models
try:
    from django.db import models
except ImportError:
    pass
