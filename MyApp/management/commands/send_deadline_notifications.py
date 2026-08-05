from django.core.management.base import BaseCommand

from MyApp.deadline_notifications import ensure_quotation_deadline_notifications


class Command(BaseCommand):
    help = 'Create deduplicated notifications for approaching quotation deadlines.'

    def handle(self, *args, **options):
        created = ensure_quotation_deadline_notifications()
        self.stdout.write(self.style.SUCCESS(f'Created {created} deadline notification(s).'))
