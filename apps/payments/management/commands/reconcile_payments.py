from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.payments.models import Payment, PaymentEvent
from apps.payments.services import paystack_verify, record_event, settle_from_paystack_data


class Command(BaseCommand):
    help = (
        'Verify pending payments with Paystack and settle any that went through, '
        'catching payments whose webhook never arrived.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--minutes',
            type=int,
            default=10,
            help='Only check payments older than this many minutes (default: 10).',
        )
        parser.add_argument(
            '--reference',
            help='Reconcile a single payment by reference instead of sweeping.',
        )

    def handle(self, *args, **options):
        payments = Payment.objects.filter(status=Payment.Status.PENDING)
        if options['reference']:
            payments = payments.filter(reference=options['reference'])
        else:
            cutoff = timezone.now() - timedelta(minutes=options['minutes'])
            payments = payments.filter(created_at__lt=cutoff)
        payments = payments.order_by('created_at')

        checked = settled = unreachable = 0
        for payment in payments:
            checked += 1
            data = paystack_verify(payment.reference)
            if data is None:
                unreachable += 1
                record_event(payment, PaymentEvent.Source.RECONCILE, 'Could not reach Paystack to verify')
                self.stderr.write(f'{payment.reference}: could not reach Paystack')
                continue
            if settle_from_paystack_data(payment, data, PaymentEvent.Source.RECONCILE):
                settled += 1
                self.stdout.write(f'{payment.reference}: {payment.get_status_display()}')

        self.stdout.write(self.style.SUCCESS(
            f'Checked {checked}, settled {settled}, unreachable {unreachable}.'
        ))
