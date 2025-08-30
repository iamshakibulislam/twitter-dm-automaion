"""
Django management command to collect followers
"""
from django.core.management.base import BaseCommand
from main.utils.follower_collector import collect_followers_sync
from main.models import LeadList

class Command(BaseCommand):
    help = 'Collect followers for a lead list using the new simple system'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--lead-list-id',
            type=int,
            help='ID of the lead list to collect followers for'
        )
        parser.add_argument(
            '--list-all',
            action='store_true',
            help='List all available lead lists'
        )
        parser.add_argument(
            '--verbose',
            action='store_true',
            help='Show detailed output'
        )
    
    def handle(self, *args, **options):
        if options['list_all']:
            self.list_lead_lists()
            return
        
        lead_list_id = options['lead_list_id']
        verbose = options['verbose']
        
        if not lead_list_id:
            self.stdout.write(
                self.style.ERROR('Please provide --lead-list-id or use --list-all to see available lists')
            )
            return
        
        try:
            lead_list = LeadList.objects.get(id=lead_list_id)
            self.stdout.write(
                self.style.SUCCESS(f'Starting follower collection for: {lead_list.name}')
            )
            
            # Collect followers
            result = collect_followers_sync(lead_list_id, verbose=verbose)
            
            if result['success']:
                self.stdout.write(
                    self.style.SUCCESS(
                        f'✅ Collection completed successfully!\n'
                        f'📊 New leads collected: {result["collected"]}\n'
                        f'📈 Total leads: {result["total_leads"]}\n'
                        f'📋 Status: {result["status"]}'
                    )
                )
            else:
                self.stdout.write(
                    self.style.ERROR(f'❌ Collection failed: {result["message"]}')
                )
                
        except LeadList.DoesNotExist:
            self.stdout.write(
                self.style.ERROR(f'Lead list with ID {lead_list_id} not found')
            )
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'Error: {str(e)}')
            )
    
    def list_lead_lists(self):
        """List all available lead lists"""
        lead_lists = LeadList.objects.all().order_by('id')
        
        if not lead_lists:
            self.stdout.write('No lead lists found')
            return
        
        self.stdout.write('Available Lead Lists:')
        self.stdout.write('=' * 50)
        
        for ll in lead_lists:
            self.stdout.write(
                f'ID: {ll.id} | Name: {ll.name} | '
                f'Status: {ll.status} | '
                f'Targets: {ll.target_usernames} | '
                f'Collected: {ll.total_collected}'
            )
