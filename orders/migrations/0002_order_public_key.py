import uuid

from django.db import migrations, models


def populate_public_keys(apps, schema_editor):
    Order = apps.get_model('orders', 'Order')
    for order in Order.objects.filter(public_key__isnull=True):
        order.public_key = uuid.uuid4()
        order.save(update_fields=['public_key'])


class Migration(migrations.Migration):
    dependencies = [
        ('orders', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='order',
            name='public_key',
            field=models.UUIDField(blank=True, editable=False, null=True),
        ),
        migrations.RunPython(populate_public_keys, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='order',
            name='public_key',
            field=models.UUIDField(default=uuid.uuid4, editable=False, unique=True, verbose_name='Публичный ключ'),
        ),
    ]
