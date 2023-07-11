# Generated by Django 3.2.17 on 2023-06-16 10:44

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('MyApp', '0014_material_required'),
    ]

    operations = [
        migrations.CreateModel(
            name='chat',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('type', models.CharField(default='', max_length=50)),
                ('message', models.CharField(default='', max_length=500)),
                ('time', models.CharField(default='', max_length=50)),
                ('date', models.CharField(max_length=100)),
                ('LOGIN', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='MyApp.login')),
                ('PROJECT', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='MyApp.project')),
            ],
        ),
    ]