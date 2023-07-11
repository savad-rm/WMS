from django.db import models

# Create your models here.

class login(models.Model):
    username=models.CharField(max_length=40)
    password=models.CharField(max_length=40)
    usertype=models.CharField(max_length=50)

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

class staff(models.Model):
    name=models.CharField(max_length=50)
    # gender=models.CharField(max_length=10)
    dob=models.CharField(max_length=20)
    phone=models.CharField(max_length=40)
    email=models.CharField(max_length=40)
    photo=models.CharField(max_length=200,default=1)
    place=models.CharField(max_length=50)
    nation=models.CharField(max_length=40)
    phone2=models.CharField(max_length=40)
    designation=models.CharField(max_length=40)
    LOGIN=models.ForeignKey(login,on_delete=models.CASCADE)

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

class schedule(models.Model):
    from_date=models.DateField(max_length=100)
    to_date=models.DateField(max_length=100)
    PROJECT= models.ForeignKey(project, on_delete=models.CASCADE)
    WORK = models.ForeignKey(work, on_delete=models.CASCADE)

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

