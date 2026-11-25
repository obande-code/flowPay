from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('businesses', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='business',
            name='webhook_url',
            field=models.URLField(blank=True, help_text='Where flowPay posts payment updates for this business.'),
        ),
    ]
