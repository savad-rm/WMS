from django.db import models
from django.utils import timezone


CAD_FILE_EXTENSIONS = frozenset(('.dwg', '.dxf'))


def _is_cad_file(file_name):
    return str(file_name).lower().endswith(tuple(CAD_FILE_EXTENSIONS))

# Create your models here.

class login(models.Model):
    username=models.EmailField(max_length=254, unique=True)
    password=models.CharField(max_length=128)
    usertype=models.CharField(max_length=50)
    api_token_version = models.PositiveIntegerField(default=0)

    @property
    def is_authenticated(self):
        """Provide the authentication contract expected by Django REST Framework."""
        return True

class project(models.Model):
    project_no=models.CharField(max_length=50)
    project_name=models.CharField(max_length=50)
    client_name=models.CharField(max_length=50)
    phone=models.BigIntegerField()
    email=models.CharField(max_length=50)
    place=models.CharField(max_length=50)
    unit_no= models.CharField(max_length=40)
    project_value=models.CharField(max_length=50)
    start_date=models.CharField(max_length=100)
    handout_date=models.CharField(max_length=100)
    project_duration=models.CharField(max_length=50)
    project_area=models.CharField(max_length=50)
    project_type=models.CharField(max_length=50)
    description=models.CharField(max_length=70)
    date=models.CharField(max_length=100)
    estimate_status=models.CharField(max_length=20)
    status=models.CharField(max_length=20)

    class Meta:
        indexes = [
            models.Index(fields=('status', 'date'), name='project_status_date_idx'),
            models.Index(fields=('project_name',), name='project_name_idx'),
            models.Index(fields=('estimate_status',), name='project_est_status_idx'),
        ]

class staff(models.Model):
    name=models.CharField(max_length=50)
    # gender=models.CharField(max_length=10)
    dob=models.CharField(max_length=20)
    phone=models.CharField(max_length=40)
    email=models.EmailField(max_length=254, unique=True)
    photo=models.CharField(max_length=200,default=1)
    place=models.CharField(max_length=50)
    nation=models.CharField(max_length=40)
    phone2=models.CharField(max_length=40)
    designation=models.CharField(max_length=40)
    LOGIN=models.ForeignKey(login,on_delete=models.CASCADE)

    class Meta:
        indexes = [
            models.Index(fields=('designation',), name='staff_designation_idx'),
            models.Index(fields=('name',), name='staff_name_idx'),
        ]

class accounthead(models.Model):
    headname=models.CharField(max_length=40)

class account_sub(models.Model):
    date=models.CharField(max_length=100)
    account_sub_name=models.CharField(max_length=40)
    amount=models.CharField(max_length=40)
    ACCOUNTHEAD=models.ForeignKey(accounthead,on_delete=models.CASCADE)

class estimate(models.Model):
    date=models.CharField(max_length=100)
    est_no=models.CharField(max_length=50)
    PROJECT=models.ForeignKey(project,on_delete=models.CASCADE)

class budget_estimate(models.Model):
    work=models.CharField(max_length=100,default="")
    work_category=models.CharField(max_length=100,default="")
    material_cost=models.CharField(max_length=40,default="")
    labour_cost=models.CharField(max_length=40,default="")
    vehicle_cost=models.CharField(max_length=40,default="")
    subcontractor_cost=models.CharField(max_length=40,default="")
    other_expenses=models.CharField(max_length=40,default="")
    total=models.CharField(max_length=40,default="")
    ESTIMATE=models.ForeignKey(estimate,on_delete=models.CASCADE,default=1)

class documents(models.Model):
    name=models.CharField(max_length=40)
    date=models.CharField(max_length=100)
    file=models.CharField(max_length=200)
    PROJECT=models.ForeignKey(project,on_delete=models.CASCADE)

class drawing(models.Model):
    file=models.CharField(max_length=200)
    date=models.CharField(max_length=100)
    PROJECT=models.ForeignKey(project,on_delete=models.CASCADE)

class inspection(models.Model):
    date=models.CharField(max_length=100)
    report=models.CharField(max_length=70)
    type=models.CharField(max_length=100)
    PROJECT=models.ForeignKey(project,on_delete=models.CASCADE)

class material(models.Model):
    name=models.CharField(max_length=40)
    unit=models.CharField(max_length=40,default="")

class material_issued(models.Model):
    date=models.CharField(max_length=100)
    quantity_issued=models.CharField(max_length=70)
    # unit=models.CharField(max_length=40,default="")
    status=models.CharField(max_length=70)
    PROJECT=models.ForeignKey(project,on_delete=models.CASCADE)
    STAFF=models.ForeignKey(staff,on_delete=models.CASCADE)
    MATERIAL=models.ForeignKey(material,on_delete=models.CASCADE)

class material_request(models.Model):
    quantity=models.CharField(max_length=40)
    # unit=models.CharField(max_length=40)
    status=models.CharField(max_length=70,default="pending")
    PROJECT= models.ForeignKey(project, on_delete=models.CASCADE)
    date=models.CharField(max_length=100)
    STAFF = models.ForeignKey(staff, on_delete=models.CASCADE)
    MATERIAL = models.ForeignKey(material, on_delete=models.CASCADE)

class material_required(models.Model):
    quantity=models.CharField(max_length=40)
    # unit=models.CharField(max_length=40,default="")
    price=models.CharField(max_length=40)
    category=models.CharField(max_length=40)
    PROJECT= models.ForeignKey(project, on_delete=models.CASCADE)
    MATERIAL = models.ForeignKey(material, on_delete=models.CASCADE)

    class Meta:
        indexes = [models.Index(fields=('PROJECT', 'category'), name='material_req_project_idx')]

class material_usage(models.Model):
    date=models.CharField(max_length=100)
    quantity=models.CharField(max_length=40)
    # unit=models.CharField(max_length=40,default="")
    PROJECT= models.ForeignKey(project, on_delete=models.CASCADE)
    STAFF = models.ForeignKey(staff, on_delete=models.CASCADE)
    MATERIAL = models.ForeignKey(material, on_delete=models.CASCADE)

class material_delivery(models.Model):
    date=models.CharField(max_length=100)
    supplier=models.CharField(max_length=40)
    place=models.CharField(max_length=40)
    # unit=models.CharField(max_length=40,default="")
    quantity=models.CharField(max_length=50)
    MATERIAL_ISSUED=models.ForeignKey(material_issued,on_delete=models.CASCADE)
    PURCHASER = models.ForeignKey(staff, on_delete=models.CASCADE)

class notification(models.Model):
    date=models.CharField(max_length=50)
    notification=models.CharField(max_length=100)
    status=models.CharField(max_length=50)
    type=models.CharField(max_length=50)
    STAFF = models.ForeignKey(staff, on_delete=models.CASCADE)
    PROJECT= models.ForeignKey(project, on_delete=models.CASCADE)

class payemnt_entry(models.Model):
    date=models.CharField(max_length=100)
    amount=models.CharField(max_length=40)
    PROJECT= models.ForeignKey(project, on_delete=models.CASCADE)

class supervisor_allocation(models.Model):
    allocated_date=models.CharField(max_length=100)
    PROJECT= models.ForeignKey(project, on_delete=models.CASCADE)
    STAFF = models.ForeignKey(staff, on_delete=models.CASCADE)

class photo(models.Model):
    date=models.CharField(max_length=100)
    photo=models.CharField(max_length=200)
    ALLOCATION=models.ForeignKey(supervisor_allocation, on_delete=models.CASCADE)
    PROJECT= models.ForeignKey(project, on_delete=models.CASCADE)

class project_manager_allocation(models.Model):
    allocated_date=models.CharField(max_length=100)
    PROJECT= models.ForeignKey(project, on_delete=models.CASCADE)
    STAFF = models.ForeignKey(staff, on_delete=models.CASCADE)

class purchaser_project_allocation(models.Model):
    allocated_date=models.CharField(max_length=100)
    PROJECT= models.ForeignKey(project, on_delete=models.CASCADE)
    STAFF = models.ForeignKey(staff, on_delete=models.CASCADE)

class work(models.Model):
    category=models.CharField(max_length=40)
    workname=models.CharField(max_length=40)
    PROJECT= models.ForeignKey(project, on_delete=models.CASCADE)

    class Meta:
        indexes = [models.Index(fields=('PROJECT', 'workname'), name='work_project_name_idx')]

class schedule(models.Model):
    from_date=models.DateField(max_length=100)
    to_date=models.DateField(max_length=100)
    PROJECT= models.ForeignKey(project, on_delete=models.CASCADE)
    WORK = models.ForeignKey(work, on_delete=models.CASCADE)

    class Meta:
        indexes = [models.Index(fields=('PROJECT', 'from_date', 'to_date'), name='schedule_project_date_idx')]

class subcontractor(models.Model):
    name=models.CharField(max_length=40)
    phone=models.CharField(max_length=40)
    email=models.CharField(max_length=40)
    place=models.CharField(max_length=40)
    # work_category=models.CharField(max_length=40)

class subcotractor_project_allocation(models.Model):
    PROJECT= models.ForeignKey(project, on_delete=models.CASCADE)
    SUBCONTRACTOR = models.ForeignKey(subcontractor, on_delete=models.CASCADE)
    amount=models.CharField(max_length=40)
    WORK = models.ForeignKey(work, on_delete=models.CASCADE)

class subcontractor_schedule(models.Model):
    from_date=models.CharField(max_length=100)
    to_date=models.CharField(max_length=100)
    SUBCONTRACTOR_PROJECT_ALLOCATION= models.ForeignKey(subcotractor_project_allocation, on_delete=models.CASCADE)

class transaction(models.Model):
    type=models.CharField(max_length=40)
    amount=models.CharField(max_length=40)
    title=models.CharField(max_length=40)
    narration=models.CharField(max_length=40)
    date=models.CharField(max_length=100)

class work_progress(models.Model):
    date = models.CharField(max_length=100)
    status=models.CharField(max_length=40)
    progress=models.CharField(max_length=50,default="")
    PROJECT= models.ForeignKey(project, on_delete=models.CASCADE)
    WORK = models.ForeignKey(work, on_delete=models.CASCADE)

    class Meta:
        indexes = [models.Index(fields=('PROJECT', 'date'), name='progress_project_date_idx')]

class worker_entry(models.Model):
    work_type=models.CharField(max_length=40)
    worker_count=models.CharField(max_length=40)
    date=models.CharField(max_length=100)
    PROJECT= models.ForeignKey(project, on_delete=models.CASCADE)

class chat(models.Model):
    type=models.CharField(max_length=50,default="")
    message=models.CharField(max_length=500,default="")
    time=models.CharField(max_length=50,default="")
    date=models.CharField(max_length=100)
    PROJECT= models.ForeignKey(project, on_delete=models.CASCADE)
    LOGIN=models.ForeignKey(login,on_delete=models.CASCADE)


# Marketing, estimation and document-control workflow.
class enquiry(models.Model):
    STATUS_CHOICES = [
        ('open', 'Open'),
        ('assigned', 'Assigned'),
        ('quoted', 'Quoted'),
        ('approved', 'Approved'),
        ('submitted', 'Submitted to client'),
        ('awarded', 'Awarded'),
        ('closed', 'Closed'),
    ]

    title = models.CharField(max_length=150)
    client_name = models.CharField(max_length=100)
    client_email = models.EmailField(blank=True)
    client_phone = models.CharField(max_length=40, blank=True)
    description = models.TextField(blank=True)
    quotation_deadline = models.DateTimeField(null=True, blank=True, db_index=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='open', db_index=True)
    created_by = models.ForeignKey(login, on_delete=models.PROTECT, related_name='created_enquiries')
    assigned_to = models.ForeignKey(staff, on_delete=models.SET_NULL, null=True, blank=True, related_name='assigned_enquiries')
    PROJECT = models.ForeignKey(project, on_delete=models.SET_NULL, null=True, blank=True, related_name='enquiries')
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ('-created_at',)


class enquiry_attachment(models.Model):
    ENQUIRY = models.ForeignKey(enquiry, on_delete=models.CASCADE, related_name='attachments')
    file = models.FileField(upload_to='enquiries/%Y/%m/')
    original_name = models.CharField(max_length=255)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    @property
    def is_cad(self):
        return _is_cad_file(self.original_name)


class enquiry_comment(models.Model):
    ENQUIRY = models.ForeignKey(enquiry, on_delete=models.CASCADE, related_name='comments')
    author = models.ForeignKey(login, on_delete=models.PROTECT)
    comment = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ('created_at',)


class quotation(models.Model):
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('manager_review', 'Manager review'),
        ('accountant_review', 'Accountant review'),
        ('approved', 'Approved'),
        ('submitted', 'Submitted to client'),
        ('accepted', 'Accepted by client'),
        ('rejected', 'Rejected'),
    ]

    ENQUIRY = models.ForeignKey(enquiry, on_delete=models.CASCADE, related_name='quotations')
    version = models.PositiveIntegerField(default=1)
    quotation_number = models.CharField(max_length=60, unique=True, null=True, blank=True)
    sequence_number = models.PositiveIntegerField(null=True, blank=True, db_index=True)
    revision = models.PositiveIntegerField(default=0)
    issue_date = models.DateField(default=timezone.localdate)
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    details = models.TextField(blank=True)
    subject = models.CharField(max_length=255, blank=True)
    client_address = models.CharField(max_length=255, blank=True)
    introduction = models.TextField(blank=True)
    validity_days = models.PositiveIntegerField(default=14)
    payment_terms = models.TextField(blank=True)
    mobilization = models.TextField(blank=True)
    variations = models.TextField(blank=True)
    client_responsibilities = models.TextField(blank=True)
    material_approval = models.TextField(blank=True)
    project_duration = models.TextField(blank=True)
    closing_text = models.TextField(blank=True)
    signatory_name = models.CharField(max_length=100, blank=True)
    signatory_title = models.CharField(max_length=100, blank=True)
    signatory_phone = models.CharField(max_length=40, blank=True)
    file = models.FileField(upload_to='quotations/%Y/%m/', blank=True)
    status = models.CharField(max_length=25, choices=STATUS_CHOICES, default='manager_review', db_index=True)
    created_by = models.ForeignKey(staff, on_delete=models.PROTECT, related_name='created_quotations')
    manager_approved_by = models.ForeignKey(staff, on_delete=models.SET_NULL, null=True, blank=True, related_name='manager_approved_quotations')
    manager_approved_at = models.DateTimeField(null=True, blank=True)
    accountant_approved_by = models.ForeignKey(staff, on_delete=models.SET_NULL, null=True, blank=True, related_name='accountant_approved_quotations')
    accountant_approved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ('-created_at',)
        constraints = [models.UniqueConstraint(fields=('ENQUIRY', 'version'), name='unique_enquiry_quotation_version')]

    @property
    def display_number(self):
        return self.quotation_number or f'Quotation {self.pk}'


class quotation_counter(models.Model):
    """Single locked row used to allocate gap-free base quotation references."""

    next_value = models.PositiveIntegerField(default=1)


class quotation_line(models.Model):
    QUOTATION = models.ForeignKey(quotation, on_delete=models.CASCADE, related_name='lines')
    item_code = models.CharField(max_length=40, blank=True)
    description = models.CharField(max_length=255)
    unit = models.CharField(max_length=30, blank=True)
    quantity = models.DecimalField(max_digits=12, decimal_places=2)
    unit_rate = models.DecimalField(max_digits=14, decimal_places=2)
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    position = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ('position', 'id')
        indexes = [models.Index(fields=('QUOTATION', 'position'), name='quotation_line_order_idx')]


class workflow_notification(models.Model):
    LEVEL_CHOICES = [
        ('info', 'Information'),
        ('warning', 'Warning'),
        ('danger', 'Urgent'),
    ]

    recipient = models.ForeignKey(login, on_delete=models.CASCADE, related_name='workflow_notifications')
    ENQUIRY = models.ForeignKey(
        enquiry, on_delete=models.CASCADE, null=True, blank=True,
        related_name='deadline_notifications',
    )
    event = models.CharField(max_length=40, default='quotation_deadline')
    level = models.CharField(max_length=10, choices=LEVEL_CHOICES, default='info')
    message = models.CharField(max_length=255)
    due_at = models.DateTimeField(null=True, blank=True)
    link = models.CharField(max_length=255, blank=True)
    dedupe_key = models.CharField(max_length=160, unique=True)
    read_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ('-created_at',)
        indexes = [
            models.Index(fields=('recipient', 'read_at', 'created_at'), name='workflow_notice_recipient_idx'),
            models.Index(fields=('event', 'due_at'), name='workflow_notice_due_idx'),
        ]

    @property
    def status(self):
        return 'read' if self.read_at else 'unread'


class costing(models.Model):
    QUOTATION = models.OneToOneField(quotation, on_delete=models.CASCADE, related_name='costing')
    material_cost = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    labour_cost = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    other_cost = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    notes = models.TextField(blank=True)
    approved_by = models.ForeignKey(staff, on_delete=models.SET_NULL, null=True, blank=True, related_name='approved_costings')
    approved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def total(self):
        return self.material_cost + self.labour_cost + self.other_cost


class project_document(models.Model):
    DOCUMENT_TYPES = [
        ('client', 'Client document'),
        ('quotation', 'Quotation'),
        ('cad', 'CAD drawing'),
        ('contract', 'Contract'),
        ('other', 'Other'),
    ]

    ENQUIRY = models.ForeignKey(enquiry, on_delete=models.CASCADE, related_name='project_documents')
    document_type = models.CharField(max_length=20, choices=DOCUMENT_TYPES, default='client')
    file = models.FileField(upload_to='project_documents/%Y/%m/')
    collected_by = models.ForeignKey(login, on_delete=models.PROTECT, related_name='collected_project_documents')
    verified_by = models.ForeignKey(staff, on_delete=models.SET_NULL, null=True, blank=True, related_name='verified_project_documents')
    verified_at = models.DateTimeField(null=True, blank=True)
    transferred_to = models.ForeignKey(project, on_delete=models.SET_NULL, null=True, blank=True, related_name='transferred_documents')
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def is_cad(self):
        return _is_cad_file(self.file.name)

