"""
Django management command for collecting leads
Run this command every 20 minutes via cron job
"""
import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from main.models import LeadList
from main.services.lead_collector import lead_collector

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Collect leads for active lead lists'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--lead-list-id',
            type=int,
            help='Collect leads for a specific lead list ID'
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force collection even if recently processed'
        )
        parser.add_argument(
            '--max-lists',
            type=int,
            default=5,
            help='Maximum number of lead lists to process in one run'
        )
        parser.add_argument(
            '--cleanup',
            action='store_true',
            help='Perform cleanup of old lead lists and error logs'
        )
    
    def handle(self, *args, **options):
        self.stdout.write(
            self.style.SUCCESS(f'Starting lead collection at {timezone.now()}')
        )
        
        try:
            if options['cleanup']:
                # Perform cleanup operations
                self._perform_cleanup()
            elif options['lead_list_id']:
                # Process specific lead list using sync method
                results = self._process_lead_lists_sync([options['lead_list_id']], force=options['force'])
                if results:
                    self._print_result(results[0], options['lead_list_id'])
            else:
                # Process multiple lead lists using sync method
                lead_lists = self._get_lead_lists_for_processing(options['max_lists'], options['force'])
                if lead_lists:
                    lead_list_ids = [lead_list.id for lead_list in lead_lists]
                    results = self._process_lead_lists_sync(lead_list_ids, force=options['force'])
                    self._print_batch_results(results)
                else:
                    self.stdout.write('No lead lists ready for processing')
                
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'Error during lead collection: {str(e)}')
            )
            logger.error(f'Lead collection error: {str(e)}')
    
    async def _process_lead_list(self, lead_list_id: int) -> dict:
        """Process a single lead list"""
        try:
            result = await lead_collector.collect_leads_for_list(lead_list_id)
            return {
                'lead_list_id': lead_list_id,
                'result': result
            }
        except Exception as e:
            return {
                'lead_list_id': lead_list_id,
                'result': {
                    'success': False,
                    'message': str(e)
                }
            }
    
    def _process_lead_lists_sync(self, lead_list_ids: list, force: bool = False) -> list:
        """Process lead lists synchronously using the batch collector"""
        try:
            # Use the batch collection method which handles threading internally
            from main.services.lead_collector import lead_collector
            
            self.stdout.write(
                f'Found {len(lead_list_ids)} lead list(s) ready for processing'
            )
            
            # Call the batch collection method which is designed to run synchronously
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
            logger.error(f'Error in batch processing: {str(e)}')
            return []
    
    async def _process_active_lead_lists(self, max_lists: int = 5, force: bool = False) -> list:
        """Process multiple active lead lists using multithreading"""
        # Get lead lists that need processing
        lead_lists = self._get_lead_lists_for_processing(max_lists, force)
        
        if not lead_lists:
            return []
        
        self.stdout.write(
            f'Found {len(lead_lists)} lead list(s) ready for processing'
        )
        
        # Extract lead list IDs
        lead_list_ids = [lead_list.id for lead_list in lead_lists]
        
        # Use the new batch collection method with multithreading
        # Note: We run this in a thread to avoid blocking the async context
        loop = asyncio.get_event_loop()
        
        def run_batch_collection():
            return lead_collector.collect_leads_batch(
                lead_list_ids, 
                max_concurrent=min(5, len(lead_list_ids))
            )
        
        # Run in thread executor to maintain async compatibility
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(run_batch_collection)
            batch_results = future.result()
        
        # Convert batch results to expected format
        processed_results = []
        for result in batch_results:
            lead_list_id = result.pop('lead_list_id', None)
            processed_results.append({
                'lead_list_id': lead_list_id,
                'result': result
            })
        
        return processed_results
    
    def _get_lead_lists_for_processing(self, max_lists: int, force: bool = False) -> list:
        """Get lead lists that are ready for processing"""
        # Base queryset for active lead lists
        queryset = LeadList.objects.filter(
            status__in=['PENDING', 'COLLECTING'],
        ).order_by('last_processed_at')
        
        # If not forcing, only get lists that haven't been processed recently
        if not force:
            twenty_minutes_ago = timezone.now() - timedelta(minutes=20)
            queryset = queryset.filter(
                last_processed_at__isnull=True,
                last_processed_at__lt=twenty_minutes_ago
            )
        
        # Limit the number of lists to process
        lead_lists = list(queryset[:max_lists])
        
        # Filter out lists that have reached their limits
        eligible_lists = []
        for lead_list in lead_lists:
            if lead_list.can_collect_more():
                eligible_lists.append(lead_list)
            else:
                # Mark as completed if limit reached
                lead_list.status = 'COMPLETED'
                lead_list.save()
                self.stdout.write(
                    f'Lead list {lead_list.id} marked as completed (limit reached)'
                )
        
        return eligible_lists
    
    def _print_result(self, result: dict, lead_list_id: int):
        """Print result for a single lead list"""
        if result['result']['success']:
            self.stdout.write(
                self.style.SUCCESS(
                    f'✅ Lead list {lead_list_id}: '
                    f"Collected {result['result'].get('collected', 0)} new leads, "
                    f"processed {result['result'].get('processed', 0)} profiles, "
                    f"total leads: {result['result'].get('total_leads', 0)}"
                )
            )
        else:
            self.stdout.write(
                self.style.ERROR(
                    f'❌ Lead list {lead_list_id}: {result["result"]["message"]}'
                )
            )
    
    def _print_batch_results(self, results: list):
        """Print results for batch processing"""
        if not results:
            self.stdout.write('No lead lists were processed')
            return
        
        total_collected = 0
        total_processed = 0
        successful = 0
        failed = 0
        
        for result in results:
            self._print_result(result, result['lead_list_id'])
            
            if result['result']['success']:
                successful += 1
                total_collected += result['result'].get('collected', 0)
                total_processed += result['result'].get('processed', 0)
            else:
                failed += 1
        
        # Print summary
        self.stdout.write('\n' + '='*50)
        self.stdout.write(f'📊 Collection Summary:')
        self.stdout.write(f'   • Lead lists processed: {len(results)}')
        self.stdout.write(f'   • Successful: {successful}')
        self.stdout.write(f'   • Failed: {failed}')
        self.stdout.write(f'   • Total leads collected: {total_collected}')
        self.stdout.write(f'   • Total profiles processed: {total_processed}')
        self.stdout.write('='*50)
    
    def _perform_cleanup(self):
        """Perform cleanup operations"""
        self.stdout.write('🧹 Starting cleanup operations...')
        
        cleanup_summary = {
            'completed_lists': 0,
            'error_lists_reset': 0,
            'old_error_messages_cleared': 0
        }
        
        # Mark old error lists for retry
        error_cutoff = timezone.now() - timedelta(hours=24)
        error_lists = LeadList.objects.filter(
            status='ERROR',
            updated_at__lt=error_cutoff
        )
        
        for lead_list in error_lists:
            if lead_list.can_collect_more():
                lead_list.status = 'PENDING'
                lead_list.error_message = ''
                lead_list.save()
                cleanup_summary['error_lists_reset'] += 1
                self.stdout.write(f'   ↻ Reset error status for lead list: {lead_list.name}')
        
        # Mark completed lists
        for lead_list in LeadList.objects.filter(status__in=['COLLECTING', 'PENDING']):
            if not lead_list.can_collect_more():
                lead_list.status = 'COMPLETED'
                lead_list.save()
                cleanup_summary['completed_lists'] += 1
                self.stdout.write(f'   ✅ Marked as completed: {lead_list.name}')
        
        # Clear old error messages from successful lists
        old_successful_lists = LeadList.objects.filter(
            status__in=['COMPLETED', 'COLLECTING'],
            error_message__isnull=False
        ).exclude(error_message='')
        
        for lead_list in old_successful_lists:
            lead_list.error_message = ''
            lead_list.save()
            cleanup_summary['old_error_messages_cleared'] += 1
        
        self.stdout.write('\n' + '='*50)
        self.stdout.write('🧹 Cleanup Summary:')
        self.stdout.write(f'   • Lists marked as completed: {cleanup_summary["completed_lists"]}')
        self.stdout.write(f'   • Error lists reset for retry: {cleanup_summary["error_lists_reset"]}')
        self.stdout.write(f'   • Old error messages cleared: {cleanup_summary["old_error_messages_cleared"]}')
        self.stdout.write('='*50)
