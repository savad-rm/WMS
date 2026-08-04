from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [('MyApp', '0019_login_api_token_version')]

    operations = [
        migrations.CreateModel(
            name='quotation_line',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('item_code', models.CharField(blank=True, max_length=40)),
                ('description', models.CharField(max_length=255)),
                ('unit', models.CharField(blank=True, max_length=30)),
                ('quantity', models.DecimalField(decimal_places=2, max_digits=12)),
                ('unit_rate', models.DecimalField(decimal_places=2, max_digits=14)),
                ('amount', models.DecimalField(decimal_places=2, max_digits=14)),
                ('position', models.PositiveIntegerField(default=0)),
                ('QUOTATION', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='lines', to='MyApp.quotation')),
            ],
            options={'ordering': ('position', 'id')},
        ),
        migrations.AddIndex(
            model_name='quotation_line',
            index=models.Index(fields=['QUOTATION', 'position'], name='quotation_line_order_idx'),
        ),
    ]
