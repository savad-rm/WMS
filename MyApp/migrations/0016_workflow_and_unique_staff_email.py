from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [('MyApp', '0015_chat')]

    operations = [
        migrations.AlterField(model_name='login', name='username', field=models.EmailField(max_length=254, unique=True)),
        migrations.AlterField(model_name='login', name='password', field=models.CharField(max_length=128)),
        migrations.AlterField(model_name='staff', name='email', field=models.EmailField(max_length=254, unique=True)),
        migrations.CreateModel(
            name='enquiry',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('title', models.CharField(max_length=150)), ('client_name', models.CharField(max_length=100)),
                ('client_email', models.EmailField(blank=True, max_length=254)), ('client_phone', models.CharField(blank=True, max_length=40)),
                ('description', models.TextField(blank=True)), ('status', models.CharField(choices=[('open','Open'),('assigned','Assigned'),('quoted','Quoted'),('approved','Approved'),('submitted','Submitted to client'),('awarded','Awarded'),('closed','Closed')], db_index=True, default='open', max_length=20)),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)), ('updated_at', models.DateTimeField(auto_now=True)),
                ('PROJECT', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='enquiries', to='MyApp.project')),
                ('assigned_to', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='assigned_enquiries', to='MyApp.staff')),
                ('created_by', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='created_enquiries', to='MyApp.login')),
            ], options={'ordering': ('-created_at',)},
        ),
        migrations.CreateModel(
            name='enquiry_attachment', fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('file', models.FileField(upload_to='enquiries/%Y/%m/')), ('original_name', models.CharField(max_length=255)), ('uploaded_at', models.DateTimeField(auto_now_add=True)),
                ('ENQUIRY', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='attachments', to='MyApp.enquiry')),
            ]),
        migrations.CreateModel(
            name='enquiry_comment', fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')), ('comment', models.TextField()), ('created_at', models.DateTimeField(auto_now_add=True)),
                ('ENQUIRY', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='comments', to='MyApp.enquiry')),
                ('author', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='MyApp.login')),
            ], options={'ordering': ('created_at',)}),
        migrations.CreateModel(
            name='quotation', fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')), ('version', models.PositiveIntegerField(default=1)),
                ('amount', models.DecimalField(decimal_places=2, max_digits=14)), ('details', models.TextField(blank=True)), ('file', models.FileField(blank=True, upload_to='quotations/%Y/%m/')),
                ('status', models.CharField(choices=[('draft','Draft'),('manager_review','Manager review'),('accountant_review','Accountant review'),('approved','Approved'),('submitted','Submitted to client'),('accepted','Accepted by client'),('rejected','Rejected')], db_index=True, default='manager_review', max_length=25)),
                ('manager_approved_at', models.DateTimeField(blank=True, null=True)), ('accountant_approved_at', models.DateTimeField(blank=True, null=True)), ('created_at', models.DateTimeField(auto_now_add=True)), ('updated_at', models.DateTimeField(auto_now=True)),
                ('ENQUIRY', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='quotations', to='MyApp.enquiry')),
                ('accountant_approved_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='accountant_approved_quotations', to='MyApp.staff')),
                ('created_by', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='created_quotations', to='MyApp.staff')),
                ('manager_approved_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='manager_approved_quotations', to='MyApp.staff')),
            ], options={'ordering': ('-created_at',), 'constraints': [models.UniqueConstraint(fields=('ENQUIRY','version'), name='unique_enquiry_quotation_version')]}),
        migrations.CreateModel(
            name='costing', fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')), ('material_cost', models.DecimalField(decimal_places=2, default=0, max_digits=14)),
                ('labour_cost', models.DecimalField(decimal_places=2, default=0, max_digits=14)), ('other_cost', models.DecimalField(decimal_places=2, default=0, max_digits=14)),
                ('notes', models.TextField(blank=True)), ('approved_at', models.DateTimeField(blank=True, null=True)), ('created_at', models.DateTimeField(auto_now_add=True)), ('updated_at', models.DateTimeField(auto_now=True)),
                ('QUOTATION', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='costing', to='MyApp.quotation')),
                ('approved_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='approved_costings', to='MyApp.staff')),
            ]),
        migrations.CreateModel(
            name='project_document', fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')), ('document_type', models.CharField(choices=[('client','Client document'),('quotation','Quotation'),('cad','CAD drawing'),('contract','Contract'),('other','Other')], default='client', max_length=20)),
                ('file', models.FileField(upload_to='project_documents/%Y/%m/')), ('verified_at', models.DateTimeField(blank=True, null=True)), ('created_at', models.DateTimeField(auto_now_add=True)),
                ('ENQUIRY', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='project_documents', to='MyApp.enquiry')),
                ('collected_by', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='collected_project_documents', to='MyApp.login')),
                ('transferred_to', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='transferred_documents', to='MyApp.project')),
                ('verified_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='verified_project_documents', to='MyApp.staff')),
            ]),
    ]
