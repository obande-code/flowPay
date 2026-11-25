from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('webhooks', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='webhookevent',
            name='digest',
            field=models.CharField(blank=True, max_length=64, null=True, unique=True),
        ),
    ]
