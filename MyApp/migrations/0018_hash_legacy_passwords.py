from django.contrib.auth.hashers import identify_hasher, make_password
from django.db import migrations


def hash_plaintext_passwords(apps, schema_editor):
    Login = apps.get_model('MyApp', 'login')
    for account in Login.objects.all().only('id', 'password').iterator():
        try:
            identify_hasher(account.password)
        except ValueError:
            account.password = make_password(account.password)
            account.save(update_fields=('password',))


class Migration(migrations.Migration):
    dependencies = [('MyApp', '0017_material_required_material_req_project_idx_and_more')]
    operations = [migrations.RunPython(hash_plaintext_passwords, migrations.RunPython.noop)]
