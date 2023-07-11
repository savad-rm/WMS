# Generated by Django 3.2.17 on 2023-05-17 11:44

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='accounthead',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('headname', models.CharField(max_length=40)),
            ],
        ),
        migrations.CreateModel(
            name='login',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('username', models.CharField(max_length=40)),
                ('password', models.CharField(max_length=40)),
                ('usertype', models.CharField(max_length=50)),
            ],
        ),
        migrations.CreateModel(
            name='material',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=40)),
                ('price', models.CharField(max_length=40)),
            ],
        ),
        migrations.CreateModel(
            name='project',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('project_name', models.CharField(max_length=50)),
                ('client_name', models.CharField(max_length=50)),
                ('phone', models.BigIntegerField()),
                ('email', models.CharField(max_length=50)),
                ('place', models.CharField(max_length=50)),
                ('unit_no', models.CharField(max_length=40)),
                ('project_value', models.CharField(max_length=50)),
                ('start_date', models.CharField(max_length=100)),
                ('handout_date', models.CharField(max_length=100)),
                ('project_duration', models.CharField(max_length=50)),
                ('project_type', models.CharField(max_length=50)),
                ('description', models.CharField(max_length=70)),
                ('date', models.CharField(max_length=100)),
                ('estimate_status', models.CharField(max_length=20)),
                ('status', models.CharField(max_length=20)),
            ],
        ),
        migrations.CreateModel(
            name='staff',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=50)),
                ('dob', models.CharField(max_length=20)),
                ('phone', models.CharField(max_length=40)),
                ('email', models.CharField(max_length=40)),
                ('photo', models.CharField(default=1, max_length=200)),
                ('place', models.CharField(max_length=50)),
                ('nation', models.CharField(max_length=40)),
                ('phone2', models.CharField(max_length=40)),
                ('designation', models.CharField(max_length=40)),
                ('LOGIN', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='MyApp.login')),
            ],
        ),
        migrations.CreateModel(
            name='subcontractor',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=40)),
                ('phone', models.CharField(max_length=40)),
                ('email', models.CharField(max_length=40)),
                ('place', models.CharField(max_length=40)),
            ],
        ),
        migrations.CreateModel(
            name='transaction',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('type', models.CharField(max_length=40)),
                ('amount', models.CharField(max_length=40)),
                ('title', models.CharField(max_length=40)),
                ('narration', models.CharField(max_length=40)),
                ('date', models.CharField(max_length=100)),
            ],
        ),
        migrations.CreateModel(
            name='work',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('category', models.CharField(max_length=40)),
                ('workname', models.CharField(max_length=40)),
                ('PROJECT', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='MyApp.project')),
            ],
        ),
        migrations.CreateModel(
            name='worker_entry',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('work_type', models.CharField(max_length=40)),
                ('worker_count', models.CharField(max_length=40)),
                ('date', models.CharField(max_length=100)),
                ('PROJECT', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='MyApp.project')),
            ],
        ),
        migrations.CreateModel(
            name='work_progress',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('date', models.CharField(max_length=100)),
                ('status', models.CharField(max_length=40)),
                ('progress', models.CharField(default='', max_length=50)),
                ('PROJECT', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='MyApp.project')),
                ('WORK', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='MyApp.work')),
            ],
        ),
        migrations.CreateModel(
            name='supervisor_allocation',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('allocated_date', models.CharField(max_length=100)),
                ('PROJECT', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='MyApp.project')),
                ('STAFF', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='MyApp.staff')),
            ],
        ),
        migrations.CreateModel(
            name='subcotractor_project_allocation',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('PROJECT', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='MyApp.project')),
                ('SUBCONTRACTOR', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='MyApp.subcontractor')),
                ('WORK', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='MyApp.work')),
            ],
        ),
        migrations.CreateModel(
            name='subcontractor_schedule',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('from_date', models.CharField(max_length=100)),
                ('to_date', models.CharField(max_length=100)),
                ('SUBCONTRACTOR_PROJECT_ALLOCATION', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='MyApp.subcotractor_project_allocation')),
            ],
        ),
        migrations.CreateModel(
            name='schedule',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('from_date', models.CharField(max_length=100)),
                ('to_date', models.CharField(max_length=100)),
                ('PROJECT', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='MyApp.project')),
                ('WORK', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='MyApp.work')),
            ],
        ),
        migrations.CreateModel(
            name='purchaser_project_allocation',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('allocated_date', models.CharField(max_length=100)),
                ('PROJECT', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='MyApp.project')),
                ('STAFF', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='MyApp.staff')),
            ],
        ),
        migrations.CreateModel(
            name='project_manager_allocation',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('allocated_date', models.CharField(max_length=100)),
                ('PROJECT', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='MyApp.project')),
                ('STAFF', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='MyApp.staff')),
            ],
        ),
        migrations.CreateModel(
            name='photo',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('date', models.CharField(max_length=100)),
                ('photo', models.CharField(max_length=200)),
                ('ALLOCATION', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='MyApp.supervisor_allocation')),
                ('PROJECT', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='MyApp.project')),
            ],
        ),
        migrations.CreateModel(
            name='payemnt_entry',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('date', models.CharField(max_length=100)),
                ('amount', models.CharField(max_length=40)),
                ('PROJECT', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='MyApp.project')),
            ],
        ),
        migrations.CreateModel(
            name='notification',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('date', models.CharField(max_length=50)),
                ('notification', models.CharField(max_length=100)),
                ('status', models.CharField(max_length=50)),
                ('type', models.CharField(max_length=50)),
                ('PROJECT', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='MyApp.project')),
            ],
        ),
        migrations.CreateModel(
            name='material_usage',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('date', models.CharField(max_length=100)),
                ('quantity', models.CharField(max_length=40)),
                ('unit', models.CharField(default='', max_length=40)),
                ('MATERIAL', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='MyApp.material')),
                ('PROJECT', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='MyApp.project')),
                ('STAFF', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='MyApp.staff')),
            ],
        ),
        migrations.CreateModel(
            name='material_required',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('quantity', models.CharField(max_length=40)),
                ('unit', models.CharField(default='', max_length=40)),
                ('MATERIAL', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='MyApp.material')),
                ('PROJECT', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='MyApp.project')),
            ],
        ),
        migrations.CreateModel(
            name='material_issued',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('date', models.CharField(max_length=100)),
                ('quantity_issued', models.CharField(max_length=70)),
                ('unit', models.CharField(default='', max_length=40)),
                ('status', models.CharField(max_length=70)),
                ('MATERIAL', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='MyApp.material')),
                ('PROJECT', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='MyApp.project')),
                ('STAFF', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='MyApp.staff')),
            ],
        ),
        migrations.CreateModel(
            name='material_delivery',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('date', models.CharField(max_length=100)),
                ('supplier', models.CharField(max_length=40)),
                ('place', models.CharField(max_length=40)),
                ('unit', models.CharField(default='', max_length=40)),
                ('quantity', models.CharField(max_length=50)),
                ('MATERIAL_ISSUED', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='MyApp.material_issued')),
                ('PURCHASER', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='MyApp.staff')),
            ],
        ),
        migrations.CreateModel(
            name='inspection',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('date', models.CharField(max_length=100)),
                ('report', models.CharField(max_length=70)),
                ('type', models.CharField(max_length=100)),
                ('PROJECT', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='MyApp.project')),
            ],
        ),
        migrations.CreateModel(
            name='estimate',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('date', models.CharField(max_length=100)),
                ('est_no', models.CharField(max_length=50)),
                ('PROJECT', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='MyApp.project')),
            ],
        ),
        migrations.CreateModel(
            name='drawing',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('file', models.CharField(max_length=200)),
                ('date', models.CharField(max_length=100)),
                ('PROJECT', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='MyApp.project')),
            ],
        ),
        migrations.CreateModel(
            name='documents',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=40)),
                ('date', models.CharField(max_length=100)),
                ('file', models.CharField(max_length=200)),
                ('PROJECT', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='MyApp.project')),
            ],
        ),
        migrations.CreateModel(
            name='budget_estimate',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('work', models.CharField(default='', max_length=100)),
                ('work_category', models.CharField(default='', max_length=100)),
                ('material_cost', models.CharField(default='', max_length=40)),
                ('labour_cost', models.CharField(default='', max_length=40)),
                ('vehicle_cost', models.CharField(default='', max_length=40)),
                ('subcontractor_cost', models.CharField(default='', max_length=40)),
                ('other_expenses', models.CharField(default='', max_length=40)),
                ('total', models.CharField(default='', max_length=40)),
                ('ESTIMATE', models.ForeignKey(default=1, on_delete=django.db.models.deletion.CASCADE, to='MyApp.estimate')),
            ],
        ),
        migrations.CreateModel(
            name='account_sub',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('date', models.CharField(max_length=100)),
                ('account_sub_name', models.CharField(max_length=40)),
                ('amount', models.CharField(max_length=40)),
                ('ACCOUNTHEAD', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='MyApp.accounthead')),
            ],
        ),
    ]
