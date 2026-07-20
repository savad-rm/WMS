from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('MyApp', '0018_hash_legacy_passwords')]

    operations = [
        migrations.AddField(
            model_name='login',
            name='api_token_version',
            field=models.PositiveIntegerField(default=0),
        ),
    ]
