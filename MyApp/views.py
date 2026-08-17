from django.core.files.storage import FileSystemStorage
from django.core.exceptions import ValidationError
from django.conf import settings
from django.http import FileResponse, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, render, redirect
from django.contrib.auth.hashers import check_password, make_password
from django.contrib.auth.password_validation import validate_password
from django.contrib import messages
from django.db import IntegrityError, transaction as db_transaction
from django.views.decorators.http import require_GET, require_POST
from io import BytesIO
from itertools import zip_longest
import re
from MyApp.middleware import legacy_role_required
from MyApp.boq_tools import (
    BOQImportError,
    build_work_packages,
    parse_boq_upload,
    suggest_material,
)

from MyApp.models import (
    account_sub,
    accounthead,
    budget_estimate,
    chat,
    documents,
    drawing,
    enquiry,
    estimate,
    inspection,
    login,
    material,
    material_delivery,
    material_issued,
    material_request,
    material_required,
    material_usage,
    notification,
    payemnt_entry,
    photo,
    project,
    project_document,
    project_manager_allocation,
    purchaser_project_allocation,
    quotation,
    schedule,
    staff,
    subcotractor_project_allocation,
    subcontractor,
    subcontractor_schedule,
    supervisor_allocation,
    transaction,
    work,
    work_progress,
    worker_entry,
)


STAFF_DESIGNATIONS = (
    'Project Manager', 'Project Engineer', 'Operation Manager', 'Supervisor',
    'Accountant', 'Purchaser', 'Marketing Executive', 'Marketing Manager',
    'Estimator', 'Document Controller',
)

USERNAME_PATTERN = re.compile(r'^[a-z0-9][a-z0-9._-]{2,49}$')


def _normalise_username(value):
    username = value.strip().lower()
    if not USERNAME_PATTERN.fullmatch(username):
        raise ValidationError(
            'Username must be 3 to 50 characters and use only lowercase letters, '
            'numbers, dots, underscores or hyphens.'
        )
    return username


def _validate_new_password(password, confirmation):
    if password != confirmation:
        raise ValidationError('Password and confirmation do not match.')
    try:
        validate_password(password)
    except ValidationError as exc:
        raise ValidationError(' '.join(exc.messages)) from exc


def _normalise_phone(value, label='Mobile number'):
    cleaned = ''.join(character for character in value.strip() if character not in ' -()')
    if cleaned.startswith('00'):
        cleaned = f'+{cleaned[2:]}'
    digits = cleaned[1:] if cleaned.startswith('+') else cleaned
    if not digits.isdigit() or not 8 <= len(digits) <= 15:
        raise ValidationError(f'{label} must contain 8 to 15 digits and may start with +.')
    return cleaned


def _posted_rows(request, *field_names):
    columns = [request.POST.getlist(name) for name in field_names]
    return [dict(zip(field_names, values)) for values in zip_longest(*columns, fillvalue='')]


def _chat_messages(project_id, current_login_id):
    """Build a chat response with a fixed number of queries."""
    messages_for_project = list(chat.objects.filter(PROJECT_id=project_id).order_by('id'))
    login_ids = {item.LOGIN_id for item in messages_for_project}
    staff_names = dict(
        staff.objects.filter(LOGIN_id__in=login_ids).values_list('LOGIN_id', 'name')
    )
    return [
        {
            'cid': item.id,
            'prid': item.PROJECT_id,
            'date': item.date,
            'time': item.time,
            'msg': item.message,
            'type': item.type,
            'login_id': item.LOGIN_id,
            'lid': current_login_id,
            'name': staff_names.get(item.LOGIN_id, ''),
        }
        for item in messages_for_project
    ]

def loginn(request):
    request.session.flush()
    return render(request, 'login.html')


def wms_home(request):
    """Resolve the legacy application root without exposing a debug 404."""
    if request.session.get('lid'):
        if request.session.get('role') in WORKFLOW_LOGIN_ROLES:
            return redirect('workflow_dashboard')
        return redirect({
            'Admin': 'Admin_home',
            'Operation Manager': 'Admin_home',
            'Project Manager': 'PMHome',
            'Project Engineer': 'PMHome',
        }.get(request.session.get('role'), 'login'))
    return redirect('login')


def _password_matches(account, raw_password):
    return bool(account and (check_password(raw_password, account.password) or account.password == raw_password))


def _change_session_password(request, failure_url):
    account = login.objects.filter(pk=request.session.get('lid')).first()
    old = request.POST.get('old', '')
    new = request.POST.get('new', '')
    confirm = request.POST.get('confirm', '')
    if not _password_matches(account, old):
        messages.error(request, 'The current password is incorrect.')
        return redirect(failure_url)
    if len(new) < 8:
        messages.error(request, 'The new password must contain at least 8 characters.')
        return redirect(failure_url)
    if new != confirm:
        messages.error(request, 'The new password and confirmation do not match.')
        return redirect(failure_url)
    account.password = make_password(new)
    account.save(update_fields=('password',))
    request.session.flush()
    messages.success(request, 'Password changed successfully. Sign in with your new password.')
    return redirect('login')

WORKFLOW_LOGIN_ROLES = {
    'Marketing Executive', 'Marketing Manager', 'Estimator', 'Document Controller',
}


def login_post(request):
    if request.method != 'POST':
        return redirect('login')
    name = request.POST.get('username', '').strip().lower()
    password = request.POST.get('password', '')
    if not name or not password:
        messages.error(request, 'Enter both username and password.')
        return render(request, 'login.html', {'username': name}, status=400)
    d=login.objects.filter(username__iexact=name).first()
    if not _password_matches(d, password):
        messages.error(request, 'Invalid username or password.')
        return render(request, 'login.html', {'username': name}, status=400)
    if d.password == password:
        d.password = make_password(password)
        d.save(update_fields=('password',))
    request.session["lid"]=d.id
    request.session["role"]=d.usertype
    s=staff.objects.filter(LOGIN=d).first()
    if s:
        request.session["sid"]=s.id
    if d.usertype=="Admin":
        return redirect('Admin_home')
    if d.usertype=="Project Manager" and s:
        return redirect('PMHome')
    if d.usertype=="Project Engineer" and s:
        return redirect('PMHome')
    if d.usertype=="Operation Manager" and s:
        return redirect('Admin_home')
    if d.usertype=="Supervisor" and s:
        return render(request,"Supervisor/spindex.html")
    if d.usertype=="Accountant" and s:
        return render(request,"Accountant/acindex.html")
    if d.usertype=="Purchaser" and s:
        return render(request,"Purchaser/pcindex.html")
    if d.usertype in WORKFLOW_LOGIN_ROLES and s:
        return redirect('workflow_dashboard')
    request.session.flush()
    messages.error(request, 'The user profile is incomplete. Contact the administrator.')
    return redirect('login')


##################################################  ADMIN  #######################################################################

@legacy_role_required('Admin')
def Admin_home(request):
    return render(request,'Admin/index.html')

def _single_project_manager():
    candidates = list(
        staff.objects.filter(designation='Project Manager')
        .select_related('LOGIN').order_by('id')[:2]
    )
    if len(candidates) == 1:
        return candidates[0], ''
    if not candidates:
        return None, 'Create one Project Manager staff account before creating a project.'
    return None, 'Automatic assignment requires exactly one Project Manager staff account.'


@legacy_role_required('Accountant')
def Add_project(request):
    default_project_manager, project_manager_error = _single_project_manager()
    return render(request,'Admin/Add Project.html', {
        'default_project_manager': default_project_manager,
        'project_manager_error': project_manager_error,
        'source_projects': project.objects.all().only('id', 'project_no', 'project_name').order_by('project_name'),
        'awarded_enquiries': enquiry.objects.filter(status='awarded', PROJECT__isnull=True).only('id', 'title', 'client_name'),
    })

@require_POST
@legacy_role_required('Accountant')
@db_transaction.atomic
def Add_project_post(request):
    default_project_manager, project_manager_error = _single_project_manager()
    if project_manager_error:
        messages.error(request, project_manager_error)
        return redirect('Add_project')
    pno=request.POST['project_no']
    pname=request.POST['t1']
    enquiry_id = request.POST.get('enquiry')
    selected_enquiry = None
    if enquiry_id:
        selected_enquiry = enquiry.objects.select_for_update().filter(
            pk=enquiry_id, status='awarded', PROJECT__isnull=True,
        ).first()
        if selected_enquiry is None:
            messages.error(request, 'That awarded enquiry has already been transferred or is no longer available.')
            return redirect('Add_project')

    client_name = selected_enquiry.client_name if selected_enquiry else request.POST['client_name']
    phone = selected_enquiry.client_phone if selected_enquiry and selected_enquiry.client_phone else request.POST['phone']
    email = (selected_enquiry.client_email if selected_enquiry and selected_enquiry.client_email else request.POST['email']).strip().lower()
    place = request.POST['place']
    unit_no = request.POST['unit_no']
    project_value = request.POST['project_value']
    starting_date = request.POST['starting_date']
    handout_date = request.POST['handout_date']
    project_duration= request.POST['project_duration']
    project_area= request.POST['project_area']
    project_type= request.POST['project_type']
    description= request.POST['textfield13']
    from datetime import datetime

    pobj=project()
    pobj.project_no=pno
    pobj.project_name=pname
    pobj.client_name=client_name
    pobj.date=datetime.now().strftime("%Y-%m-%d")
    pobj.phone=phone
    pobj.email=email
    pobj.place=place
    pobj.unit_no=unit_no
    pobj.project_value=project_value
    pobj.start_date=starting_date
    pobj.handout_date=handout_date
    pobj.project_duration=project_duration
    pobj.project_area=project_area
    pobj.project_type=project_type
    pobj.description=description
    pobj.estimate_status='pending'
    # Automatic Project Manager assignment replaces the former manual step,
    # which also moved a newly-created project into the ongoing portfolio.
    pobj.status='ongoing'
    pobj.save()
    project_manager_allocation.objects.create(
        allocated_date=pobj.date,
        PROJECT=pobj,
        STAFF=default_project_manager,
    )

    # Optionally reuse an existing project's planning data without sharing rows.
    source_id = request.POST.get('source_project')
    if source_id:
        source = project.objects.filter(pk=source_id).first()
        if source:
            work_map = {}
            if request.POST.get('copy_scope'):
                for old_work in work.objects.filter(PROJECT=source):
                    work_map[old_work.id] = work.objects.create(
                        PROJECT=pobj, category=old_work.category, workname=old_work.workname
                    )
            if request.POST.get('copy_materials'):
                material_required.objects.bulk_create([
                    material_required(PROJECT=pobj, MATERIAL=item.MATERIAL, quantity=item.quantity,
                                      price=item.price, category=item.category)
                    for item in material_required.objects.filter(PROJECT=source).select_related('MATERIAL')
                ])
            if request.POST.get('copy_schedule'):
                if not work_map:
                    for old_work in work.objects.filter(PROJECT=source):
                        work_map[old_work.id] = work.objects.create(
                            PROJECT=pobj, category=old_work.category, workname=old_work.workname
                        )
                copied_schedules = [
                    schedule(PROJECT=pobj, WORK=work_map[item.WORK_id],
                             from_date=item.from_date, to_date=item.to_date)
                    for item in schedule.objects.filter(PROJECT=source).select_related('WORK')
                ]
                schedule.objects.bulk_create(copied_schedules)
                work_progress.objects.bulk_create([
                    work_progress(PROJECT=pobj, WORK=item.WORK, date=pobj.date,
                                  status='pending', progress='0')
                    for item in copied_schedules
                ])

    if selected_enquiry:
        selected_enquiry.PROJECT = pobj
        selected_enquiry.save(update_fields=('PROJECT', 'updated_at'))
        selected_enquiry.project_documents.update(transferred_to=pobj)

    messages.success(
        request,
        f'Project added successfully and assigned to {default_project_manager.name}.',
    )
    return redirect('View_all_projects')

@legacy_role_required('Admin')
def Add_staff(request):
    return render(request,'Admin/Add Staff.html', {'designations': STAFF_DESIGNATIONS})

@require_POST
@legacy_role_required('Admin')
def Add_staff_post(request):
    name = request.POST['name']
    dob = request.POST['dob']
    # gender = request.POST['RadioGroup1']
    phone = request.POST['phone']
    email = request.POST['email'].strip().lower()
    photo = request.FILES.get('photo')
    place = request.POST['place']
    nation = request.POST['nation']
    phone2 = request.POST['phone2']
    designation = request.POST['designation']
    username = request.POST.get('username', '')
    password = request.POST.get('password', '')
    password_confirmation = request.POST.get('password_confirmation', '')

    from datetime import datetime
    form_context = {'form_data': request.POST, 'designations': STAFF_DESIGNATIONS}
    try:
        username = _normalise_username(username)
        _validate_new_password(password, password_confirmation)
        phone = _normalise_phone(phone)
        phone2 = _normalise_phone(phone2, 'Home contact') if phone2.strip() else ''
    except ValidationError as exc:
        return render(request, 'Admin/Add Staff.html', {
            **form_context, 'error': exc.messages[0],
        }, status=400)
    if designation not in STAFF_DESIGNATIONS:
        return render(request, 'Admin/Add Staff.html', {
            **form_context, 'error': 'Select a valid staff role.',
        }, status=400)
    if login.objects.filter(username__iexact=username).exists():
        return render(request, 'Admin/Add Staff.html', {
            **form_context, 'error': 'This username is already in use.',
        }, status=400)
    if staff.objects.filter(email__iexact=email).exists():
        return render(request, 'Admin/Add Staff.html', {
            **form_context, 'error': 'A staff profile with this email already exists.',
        }, status=400)
    fs = FileSystemStorage()
    photo_url = ''
    if photo:
        filename=datetime.now().strftime("%Y%m%d%H%M%S")+photo.name
        saved_name=fs.save(filename,photo)
        photo_url=fs.url(saved_name)
    try:
        with db_transaction.atomic():
            lobj = login.objects.create(
                username=username, password=make_password(password), usertype=designation,
            )
            staff.objects.create(
                LOGIN=lobj, name=name, dob=dob, phone=phone, email=email, photo=photo_url,
                place=place, nation=nation, phone2=phone2, designation=designation,
            )
    except IntegrityError:
        return render(request, 'Admin/Add Staff.html', {
            **form_context, 'error': 'The username or email is already in use.',
        }, status=400)
    messages.success(request, 'Staff added successfully.')
    return redirect('View_Staff')

def Edit_Projec_allocation_to_pm(request,id):
    res=project_manager_allocation.objects.get(pk=id)
    res2=staff.objects.filter(designation='Project Manager')
    return render(request,'Admin/Edit Project allocation to pm.html',{'data':res,'data1':res2})

def Edit_Projec_allocation_to_pm_post(request):
    pid=request.POST['pid']
    m=request.POST['pm']
    pm=staff.objects.get(pk=m)
    project_manager_allocation.objects.filter(pk=pid).update(STAFF=pm)
    return HttpResponse("<script>alert('Edited Successfully');window.location='/WMS/View_Ongoing_projects/'</script>")

def Delete_pma(request,id):
    project_manager_allocation.objects.filter(pk=id).delete()
    return HttpResponse("<script>alert('Deleted Successfully');window.location='/WMS/View_Ongoing_projects/'</script>")

def Edit_Projec_allocation_to_supervisor(request,id):
    res = supervisor_allocation.objects.get(pk=id)
    res2 = staff.objects.filter(designation='Supervisor')
    return render(request,'Admin/Edit Project Allocation to Supervisor.html',{'data':res,'data1':res2})

def Edit_Projec_allocation_to_supervisor_post(request):
    pid=request.POST['pid']
    sup = request.POST['supervisor']
    s=staff.objects.get(pk=sup)
    supervisor_allocation.objects.filter(pk=pid).update(STAFF = s)
    return HttpResponse("<script>alert('Edited Successfully');window.location='/WMS/View_Ongoing_projects/'</script>")

def Delete_psa(request,id):
    supervisor_allocation.objects.filter(pk=id).delete()
    return HttpResponse("<script>alert('Deleted Successfully');window.location='/WMS/View_Ongoing_projects/'</script>")

def Edit_project(request,id):
    res=project.objects.get(pk=id)
    return render(request,'Admin/Edit Project.html',{'data':res})

def Edit_project_post(request):
    pid=request.POST['pid']
    project_name=request.POST['project_name']
    client_name = request.POST['client_name']
    phone = request.POST['phone']
    email = request.POST['email']
    place = request.POST['place']
    unit_no = request.POST['unit_no']
    project_value = request.POST['project_value']
    starting_date = request.POST['starting_date']
    handout_date = request.POST['handout_date']
    project_duration= request.POST['project_duration']
    project_type= request.POST['project_type']
    description= request.POST['description']
    estimate_status = request.POST['estimate_status']
    status = request.POST['status']
    project.objects.filter(id=pid).update(project_name = project_name,client_name = client_name,phone = phone,email = email,place = place,unit_no = unit_no,project_value = project_value,start_date = starting_date,handout_date=handout_date,project_duration = project_duration,project_type=project_type,description = description,estimate_status = estimate_status,status=status)
    return HttpResponse("<script>alert('Project Edited');window.location='/WMS/View_Project/'</script>")

def Delete_project(request,id):
    project.objects.filter(pk=id).delete()
    return HttpResponse("<script>alert('Project Deleted');window.location='/WMS/View_Project/'</script>")

@legacy_role_required('Admin')
def Edit_staff(request,id):
    res=get_object_or_404(staff, pk=id)
    return render(request,'Admin/Edit Staff.html',{'data':res, 'designations': STAFF_DESIGNATIONS})

@require_POST
@legacy_role_required('Admin')
def Edit_staff_post(request):
    sid=request.POST['sid']
    name = request.POST['name']
    dob = request.POST['dob']
    # gender = request.POST['RadioGroup1']
    phone = request.POST['phone']
    email = request.POST['email'].strip().lower()
    place = request.POST['place']
    nation = request.POST['nation']
    phone2 = request.POST['phone2']
    designation = request.POST['designation']
    username = request.POST.get('username', '')
    new_password = request.POST.get('password', '')
    password_confirmation = request.POST.get('password_confirmation', '')
    current_staff = staff.objects.select_related('LOGIN').get(pk=sid)
    try:
        # Legacy accounts may still use an email address as their username. They
        # remain valid until an administrator deliberately assigns a modern ID.
        if username.strip().lower() == current_staff.LOGIN.username.lower():
            username = current_staff.LOGIN.username
        else:
            username = _normalise_username(username)
        if new_password or password_confirmation:
            _validate_new_password(new_password, password_confirmation)
        phone = _normalise_phone(phone)
        phone2 = _normalise_phone(phone2, 'Home contact') if phone2.strip() else ''
    except ValidationError as exc:
        messages.error(request, exc.messages[0])
        return redirect('Edit_staff', id=sid)
    if designation not in STAFF_DESIGNATIONS:
        messages.error(request, 'Select a valid staff role.')
        return redirect('Edit_staff', id=sid)
    if login.objects.filter(username__iexact=username).exclude(pk=current_staff.LOGIN_id).exists():
        messages.error(request, 'This username is already in use.')
        return redirect('Edit_staff', id=sid)
    if staff.objects.filter(email__iexact=email).exclude(pk=sid).exists():
        messages.error(request, 'A staff profile with this email already exists.')
        return redirect('Edit_staff', id=sid)
    updates = dict(name=name, dob=dob, phone=phone, email=email, place=place,
                   phone2=phone2, nation=nation, designation=designation)
    if 'photo' in request.FILES:
        photo = request.FILES['photo']
        from datetime import datetime
        fs = FileSystemStorage()
        date = datetime.now().strftime("%Y%m%d%H%M%S") + photo.name
        fn = fs.save(date, photo)
        updates['photo'] = fs.url(fn)
    with db_transaction.atomic():
        staff.objects.filter(id=sid).update(**updates)
        account_updates = {'username': username, 'usertype': designation}
        if new_password:
            account_updates.update({
                'password': make_password(new_password),
                'api_token_version': current_staff.LOGIN.api_token_version + 1,
            })
        login.objects.filter(pk=current_staff.LOGIN_id).update(**account_updates)
    messages.success(request, 'Staff updated successfully.')
    return redirect('View_Staff')

@require_POST
@legacy_role_required('Admin')
def Delete_staff(request,id,lid):
    login.objects.get(pk=lid).delete()
    staff.objects.filter(id=id).delete()
    messages.success(request, 'Staff deleted successfully.')
    return redirect('View_Staff')

def Delete_chata(request,id,pid):
    lid=request.session['lid']
    chat.objects.filter(id=id).delete()
    p=project.objects.get(id=pid).project_name
    return render(request,'Admin/fur_chat.html', {'id':pid,'lid':lid,'p':p})

def chatsa(request,id,msg):
    lid=request.session['lid']
    from datetime import datetime

    d=chat()
    d.LOGIN_id=lid
    d.PROJECT_id=id
    d.message=msg
    d.date=datetime.now().strftime("%Y-%m-%d")
    d.time=datetime.now().strftime("%I:%M %p")
    d.type="admin"
    d.save()
    return JsonResponse({'status':'ok'})

def chata(request,id):
    p=project.objects.get(id=id).project_name
    return render(request,'Admin/fur_chat.html', {'id':id,'p':p})

def viewmsg_admin(request,id):
    return JsonResponse({'data': _chat_messages(id, request.session['lid'])})

def viewmsg(request,id):
    res = chat.objects.filter(PROJECT_id=id)
    l = []
    for i in res:
        l.append({'prid':i.PROJECT_id, 'date':i.date, 'time':i.time, 'msg':i.message, 'type':i.type, 'login_id':i.LOGIN_id, 'lid':request.session['lid']})
    return JsonResponse({'data':l})


def Projec_allocation_to_project_manager(request,id):
    res=staff.objects.filter(designation='Project Manager')
    res1=project.objects.get(pk=id)
    return render(request,'Admin/Project allocation to project manager.html',{'data':res,'data1':res1})

def Projec_allocation_to_project_manager_post(request):
    pid=request.POST['pid']
    res=project.objects.get(pk=pid)
    manager_id=request.POST['project_manager']
    res1=staff.objects.get(pk=manager_id)
    from datetime import datetime
    pm=project_manager_allocation()
    pm.PROJECT=res
    pm.STAFF=res1
    pm.allocated_date=datetime.now().strftime("%Y-%m-%d")
    pm.save()
    project.objects.filter(id=pid).update(status='ongoing')
    return HttpResponse("<script>alert('Allocated Project Manager');window.location='/WMS/View_Project/'</script>")

def Projec_allocation_to_supervisor(request,id):
    res=staff.objects.filter(designation='Supervisor')
    res1=project.objects.get(pk=id)
    return render(request,'Admin/Project Allocation to Supervisor.html',{'data':res,'data1':res1})

def Projec_allocation_to_supervisor_post(request):
    pid=request.POST['pid']
    res=project.objects.get(pk=pid)
    supervisor_id = request.POST['supervisor']
    res1 = staff.objects.get(pk=supervisor_id)
    from datetime import datetime
    ps = supervisor_allocation()
    ps.PROJECT = res
    ps.STAFF = res1
    ps.allocated_date =datetime.now().strftime("%Y-%m-%d")
    ps.save()
    ps = project.objects.filter(id=pid).update(status='ongoing')
    return HttpResponse("<script>alert('Allocated Supervisor');window.location='/WMS/View_Project/'</script>")

def View_account_reports(request):
    res=account_sub.objects.all()
    return render(request,'Admin/View Account Reports.html',{'data':res})

def search_acnts(request):
    frm = request.POST['from']
    to = request.POST['to']
    res = account_sub.objects.filter(date__range=[frm,to])
    return render(request, 'Admin/View Account Reports.html', {'data': res})

def View_all_subcontractors(request):
    res=subcontractor.objects.all()
    return render(request,'Admin/View All Subcontractors.html',{'data':res})

def search_sbcr(request):
    w=request.POST['text']
    res = subcontractor.objects.filter(name__icontains=w)
    return render(request, 'Admin/View All Subcontractors.html', {'data': res})

def View_Budget(request,id):
    res=budget_estimate.objects.filter(ESTIMATE=id)
    return render(request, 'Admin/View Budget.html', {'data':res, 'id':id})

def search_bgta(request):
    id = request.POST['id']
    c=request.POST['textfield']
    res = budget_estimate.objects.filter(work_category__icontains=c,ESTIMATE=id)
    return render(request, 'Admin/View Budget.html', {'data':res, 'id':id})

def View_Estimatead(request,id):
    res=estimate.objects.filter(PROJECT=id)
    tt=[]
    for i in res:
        j=budget_estimate.objects.filter(ESTIMATE_id=i.id)
        myval=0
        for k in j:
            myval+=float(k.total)
        tt.append({"id":i.id,"date":i.date,"est_no":i.est_no,"PROJECT":i.PROJECT.id,"my":myval})
    res2 = project.objects.get(id=id, status='ongoing')
    return render(request, 'Admin/View Estimate.html',{'data':res2,'data2':tt,'id':id})

def search_estad(request):
    id = request.POST['pid']
    p = project.objects.get(pk=id)
    frm = request.POST['from']
    to = request.POST['to']
    res = estimate.objects.filter(PROJECT=p,date__range=[frm,to])
    tt = []
    for i in res:
        j = budget_estimate.objects.filter(ESTIMATE_id=i.id)
        myval = 0
        for k in j:
            myval += float(k.total)
        tt.append({"id": i.id, "date": i.date, "est_no": i.est_no, "PROJECT": i.PROJECT.id, "my": myval})
    res2 = project.objects.get(id=id, status='ongoing')
    return render(request, 'Admin/View Estimate.html', {'data': res2,'data2':tt,'id':id})

def approve_est(request,id):
    project.objects.filter(pk=id).update(estimate_status='approved')
    return HttpResponse("<script>alert('Approved');window.location='/WMS/View_Ongoing_projects/'</script>")

def reject_est(request,id):
    project.objects.filter(pk=id).update(estimate_status='rejected')
    return HttpResponse("<script>alert('Rejected');window.location='/WMS/View_Ongoing_projects/'</script>")

def View_Material_required(request,id):
    res=material_required.objects.filter(PROJECT=id)
    res2 = project.objects.get(id=id, status='ongoing')
    return render(request,'Admin/View Material Required.html',{'data':res2,'data2':res,'id':id})

def search_msda(request):
    id = request.POST['id']
    p=project.objects.get(pk=id)
    txt = request.POST['text']
    res = material_required.objects.filter(MATERIAL__name__icontains=txt,PROJECT=p)
    res2 = project.objects.get(id=id, status='ongoing')
    return render(request, 'Admin/View Material Required.html', {'data': res2,'data2':res, 'id': id})

def View_Ongoing_projects(request):
    res=project.objects.filter(status='ongoing')
    return render(request,'Admin/View Ongoing Projects.html',{'data':res})

def search_prjcts(request):
    button=request.POST['button']
    if button == 'Search':
        txt=request.POST['text']
        res = project.objects.filter(status='ongoing',project_name__icontains=txt)
        return render(request, 'Admin/View Ongoing Projects.html', {'data': res})
    else:
        frm=request.POST['from']
        to=request.POST['to']
        res = project.objects.filter(status='ongoing',date__range=[frm,to])
        return render(request, 'Admin/View Ongoing Projects.html', {'data': res})

def View_Payment_Entry(request,id):
    res=payemnt_entry.objects.filter(PROJECT=id)
    res2 = project.objects.get(id=id, status='ongoing')
    return render(request,'Admin/View Payment Entry.html',{'data':res2,'data2':res,'id':id})

def search_pmnte(request):
    id=request.POST['pid']
    p = project.objects.get(id=id)
    frm=request.POST['from']
    to=request.POST['to']
    res = payemnt_entry.objects.filter(date__range=[frm,to],PROJECT=p)
    res2 = project.objects.get(id=id, status='ongoing')
    return render(request, 'Admin/View Payment Entry.html', {'data': res2,'data2':res, 'id': id})

def View_Project_allocated_to_project_manager(request,id):
    res=project_manager_allocation.objects.filter(PROJECT=id)
    res2 = project.objects.get(id=id, status='ongoing')
    return render(request,'Admin/View Project Allocated to Project Manager.html',{'data':res2,"data2":res,'id':id})

def search_pmr(request):
    id = request.POST['pid']
    p = project.objects.get(pk=id)
    w=request.POST['text']
    res = project_manager_allocation.objects.filter(PROJECT=p,STAFF__name__icontains=w)
    res2 = project.objects.get(id=id, status='ongoing')
    return render(request, 'Admin/View Project Allocated to Project Manager.html', {'data': res2,"data2":res, 'id': id})

def View_Project_allocated_to_supervisor(request,id):
    res=supervisor_allocation.objects.filter(PROJECT=id)
    res2 = project.objects.get(id=id, status='ongoing')
    return render(request,'Admin/View Project Allocated to Supervisor.html',{'data':res2,'data2':res,'id':id})

def search_spra(request):
    id = request.POST['pid']
    p = project.objects.get(pk=id)
    w=request.POST['text']
    res = supervisor_allocation.objects.filter(PROJECT=p,STAFF__name__icontains=w)
    res2 = project.objects.get(id=id, status='ongoing')
    return render(request, 'Admin/View Project Allocated to Supervisor.html', {'data': res2,'data2':res, 'id': id})

def View_Project(request):
    res=project.objects.all()
    return render(request,'Admin/View Project.html',{'data':res})

def search_prjts(request):
    button=request.POST['button']
    if button == 'Search':
        txt=request.POST['text']
        res = project.objects.filter(project_name__icontains=txt)
        return render(request, 'Admin/View Project.html', {'data': res})
    else:
        frm=request.POST['from']
        to=request.POST['to']
        res = project.objects.filter(date__range=[frm,to])
        return render(request, 'Admin/View Project.html', {'data': res})

def View_projects_functions(request,id):
    res=project.objects.get(id=id,status='ongoing')
    return render(request,'Admin/View Projects Functions.html',{'data':res})

def View_Completed_Projects(request):
    res=project.objects.filter(status='Completed')
    return render(request,'Admin/View Completed Project.html',{'data':res})

def search_prjtscd(request):
    button=request.POST['button']
    if button == 'Search':
        txt=request.POST['text']
        res = project.objects.filter(status='completed',project_name__icontains=txt)
        return render(request, 'Admin/View Completed Project.html', {'data': res})
    else:
        frm=request.POST['from']
        to=request.POST['to']
        res = project.objects.filter(status='completed',date__range=[frm,to])
        return render(request, 'Admin/View Completed Project.html', {'data': res})

def View_Schedule(request,id):
    res=schedule.objects.filter(PROJECT=id)
    res2 = project.objects.get(id=id, status='ongoing')
    return render(request,'Admin/View Schedule.html',{'data':res2,'data2':res,'id':id})

def schedule_searcha(request):
    id = request.POST['pid']
    P = project.objects.get(id=id)
    frm=request.POST['from']
    to=request.POST['to']
    res=schedule.objects.filter(from_date__range=[frm,to],to_date__range=[frm,to],PROJECT=P)
    res2 = project.objects.get(id=id, status='ongoing')
    return render(request, 'Admin/View Schedule.html', {'data': res2,'data2':res,'id':id})

@legacy_role_required('Admin')
def View_Staff(request):
    res=staff.objects.all()
    return render(request,'Admin/View Staff.html',{'data':res})

@legacy_role_required('Admin')
def search_staff(request):
    w=request.POST['text']
    res = staff.objects.filter(name__icontains=w)
    return render(request, 'Admin/View Staff.html', {'data': res})

def View_Subcontractor_datails_of_project(request,id):
    res=subcotractor_project_allocation.objects.filter(PROJECT=id)
    res2 = project.objects.get(id=id, status='ongoing')
    return render(request,'Admin/View Subcontractor Details of Project.html',{'data':res2,'data2':res,'id':id})

def search_sbcrp(request):
    id = request.POST['pid']
    p = project.objects.get(pk=id)
    w=request.POST['text']
    res = subcotractor_project_allocation.objects.filter(PROJECT=p,SUBCONTRACTOR__name__icontains=w)
    res2 = project.objects.get(id=id, status='ongoing')
    return render(request, 'Admin/View Subcontractor Details of Project.html', {'data': res2,'data2':res,'id':id})

def View_Total_material_request(request,id):
    res=material_request.objects.filter(PROJECT=id)
    res2 = project.objects.get(id=id, status='ongoing')
    return render(request,'Admin/View Total Material Request.html',{'data':res2,'data2':res,'id':id})

def search_mrqt(request):
    button = request.POST['button']
    if button == 'Search':
        id = request.POST['pid']
        p = project.objects.get(pk=id)
        txt = request.POST['text']
        res = material_request.objects.filter(PROJECT=p, MATERIAL__name__icontains=txt)
        res2 = project.objects.get(id=id, status='ongoing')
        return render(request, 'Admin/View Total Material Request.html', {'data': res2,'data2':res, 'id': id})
    else:
        id = request.POST['pid']
        p = project.objects.get(pk=id)
        frm = request.POST['from']
        to = request.POST['to']
        res = material_request.objects.filter(PROJECT=p, date__range=[frm, to])
        res2 = project.objects.get(id=id, status='ongoing')
        return render(request, 'Admin/View Total Material Request.html', {'data': res2,'data2':res, 'id': id})

def View_Total_worker_report(request,id):
    res=worker_entry.objects.filter(PROJECT=id)
    res2 = project.objects.get(id=id, status='ongoing')
    return render(request,'Admin/View Total Worker Reports.html',{'data':res2,'data2':res,'id':id})

def search_twcr(request):
    button=request.POST['button']
    if button == "Search":
        id = request.POST['pid']
        p = project.objects.get(id=id)
        frm=request.POST['from']
        to=request.POST['to']
        res = worker_entry.objects.filter(date__range=[frm,to],PROJECT=p)
        res2 = project.objects.get(id=id, status='ongoing')
        return render(request, 'Admin/View Total Worker Reports.html', {'data': res2,'data2':res, 'id': id})
    else:
        id = request.POST['pid']
        p = project.objects.get(id=id)
        text=request.POST['txt']
        res = worker_entry.objects.filter(work_type__icontains=text, PROJECT=p)
        res2 = project.objects.get(id=id, status='ongoing')
        return render(request, 'Admin/View Total Worker Reports.html', {'data': res2,'data2':res, 'id': id})

def View_Work_management(request,id):
    res=work.objects.filter(PROJECT=id)
    res2 = project.objects.get(id=id, status='ongoing')
    return render(request,'Admin/View Work Management.html',{'data':res2,'data2':res,'id':id})

def search_worka(request):
    id = request.POST['pid']
    p = project.objects.get(id=id)
    w=request.POST['textfield']
    res=work.objects.filter(workname__icontains=w,PROJECT=p)
    res2 = project.objects.get(id=id, status='ongoing')
    return render(request, 'Admin/View Work Management.html', {'data': res2,'data2':res, 'id': id})

def View_Work_progress(request,id):
    res=work_progress.objects.filter(PROJECT=id)
    res2 = project.objects.get(id=id, status='ongoing')
    l = []
    for i in res:
        ws = schedule.objects.filter(WORK=i.WORK,PROJECT=i.PROJECT)
        if ws.exists():
            a = ws[0].to_date
            import datetime
            to_date = datetime.datetime.strftime(a,'%Y-%m-%d')
            today = datetime.datetime.now().strftime("%Y-%m-%d")
            if to_date >  today:
                ss="ok"
                from datetime import datetime as dt
                res = (dt.strptime(to_date, "%Y-%m-%d") - dt.strptime(today, "%Y-%m-%d")).days
                if res <3:
                    ss="not"
                    if i.status == "Completed":
                        ss = "ok"
                else:
                    ss="ok"
            else:
                if i.status=="Completed":
                    ss="ok"
                else:
                    ss="no"
            l.append({'ss':ss,'WORK':i.WORK,'date':i.date,'status':i.status,'progress':i.progress,'todate':to_date})
    return render(request,'Admin/View Work Progress.html',{'data':res2,'data2':l,'id':id})

def search_prsta(request):
    button=request.POST['button']
    if button == 'Search':
        id = request.POST['pid']
        p = project.objects.get(id=id)
        txt=request.POST['text']
        res = work_progress.objects.filter(PROJECT=p,WORK__workname__icontains=txt)
        res2 = project.objects.get(id=id, status='ongoing')
        l = []
        for i in res:
            ws = schedule.objects.filter(WORK=i.WORK, PROJECT=i.PROJECT)
            if ws.exists():
                a = ws[0].to_date
                import datetime
                to_date = datetime.datetime.strftime(a, '%Y-%m-%d')
                today = datetime.datetime.now().strftime("%Y-%m-%d")
                if to_date > today:
                    ss = "ok"
                    from datetime import datetime as dt
                    res = (dt.strptime(to_date, "%Y-%m-%d") - dt.strptime(today, "%Y-%m-%d")).days
                    if res < 3:
                        ss = "not"
                        if i.status == "Completed":
                            ss = "ok"
                    else:
                        ss = "ok"
                else:
                    if i.status == "Completed":
                        ss = "ok"
                    else:
                        ss = "no"
                l.append({'ss': ss, 'WORK': i.WORK, 'date': i.date, 'status': i.status, 'progress': i.progress,'todate': to_date})
        return render(request, 'Admin/View Work Progress.html', {'data': res2,'data2':l, 'id': id})
    else:
        id = request.POST['pid']
        p = project.objects.get(id=id)
        frm=request.POST['from']
        to=request.POST['to']
        res = work_progress.objects.filter(PROJECT=p,date__range=[frm,to])
        res2 = project.objects.get(id=id, status='ongoing')
        l = []
        for i in res:
            ws = schedule.objects.filter(WORK=i.WORK, PROJECT=i.PROJECT)
            if ws.exists():
                a = ws[0].to_date
                import datetime
                to_date = datetime.datetime.strftime(a, '%Y-%m-%d')
                today = datetime.datetime.now().strftime("%Y-%m-%d")
                if to_date > today:
                    ss = "ok"
                    from datetime import datetime as dt
                    res = (dt.strptime(to_date, "%Y-%m-%d") - dt.strptime(today, "%Y-%m-%d")).days
                    if res < 3:
                        ss = "not"
                        if i.status == "Completed":
                            ss = "ok"
                    else:
                        ss = "ok"
                else:
                    if i.status == "Completed":
                        ss = "ok"
                    else:
                        ss = "no"
                l.append({'ss': ss, 'WORK': i.WORK, 'date': i.date, 'status': i.status, 'progress': i.progress,'todate': to_date})
        return render(request, 'Admin/View Work Progress.html', {'data': res2,'data2':l, 'id': id})

def View_Worksite_photos(request,id):
    res=photo.objects.filter(PROJECT=id)
    res2 = project.objects.get(id=id, status='ongoing')
    return render(request,'Admin/View Worksite Photos.html',{'data':res2,'data2':res,'id':id})

def search_sp(request):
    id = request.POST['pid']
    p = project.objects.get(id=id)
    frm=request.POST['from']
    to=request.POST['to']
    res = photo.objects.filter(date__range=[frm,to],PROJECT=p)
    res2 = project.objects.get(id=id, status='ongoing')
    return render(request, 'Admin/View Worksite Photos.html', {'data': res2,'data2':res, 'id': id})

##################################################  PROJECT MANAGER  #######################################################################

def PMHome(request):
    return render(request,'Project Manager/pmindex.html')

def Add_Estimate(request,id):
    res=project.objects.get(id=id)
    return render(request,'Project Manager/Add Estimate.html',{'data':res})

def Add_Estimate_post(request):
    pid=request.POST['pid']
    p=project.objects.get(pk=pid)
    est=request.POST['est']
    from datetime import datetime

    amrj=estimate()
    amrj.est_no=est
    amrj.PROJECT=p
    amrj.date=datetime.now().strftime("%Y-%m-%d")
    amrj.save()
    request.session['eid']=amrj.id
    id= request.session['eid']
    return HttpResponse("<script>alert('Added Successfully');window.location='/WMS/Draft_budget/"+str(id)+"'</script>")

@legacy_role_required('Project Manager')
def Add_material_required(request,id):
    res=project.objects.get(id=id)
    res2=material.objects.all().order_by('name')
    source_projects = project.objects.exclude(id=id).only('id', 'project_no', 'project_name').order_by('project_name')
    return render(request,'Project Manager/Add Material Required.html',{
        'data':res, 'data2':res2, 'source_projects':source_projects,
    })

@require_POST
@legacy_role_required('Project Manager')
@db_transaction.atomic
def Add_material_required_post(request):
    pid=request.POST['pid']
    p=project.objects.get(pk=pid)
    categories=request.POST.getlist('category')
    material_ids=request.POST.getlist('material')
    quantities=request.POST.getlist('quantity')
    prices=request.POST.getlist('price')
    form_rows = _posted_rows(request, 'category', 'material', 'quantity', 'price')

    def form_error(message):
        messages.error(request, message)
        return render(request, 'Project Manager/Add Material Required.html', {
            'data': p, 'data2': material.objects.all().order_by('name'),
            'source_projects': project.objects.exclude(id=p.pk).only('id', 'project_no', 'project_name').order_by('project_name'),
            'form_rows': form_rows,
        }, status=400)

    if not (len(categories) == len(material_ids) == len(quantities) == len(prices)):
        return form_error('Material row data is incomplete.')
    try:
        normalized_material_ids = [int(value) for value in material_ids]
    except (TypeError, ValueError):
        return form_error('Every material row must reference a valid material.')
    material_map = material.objects.in_bulk(normalized_material_ids)
    rows=[]
    for category, material_id, quantity, price in zip(categories, normalized_material_ids, quantities, prices):
        if not all((category.strip(), material_id, quantity, price)) or material_id not in material_map:
            return form_error('Every material row must be complete.')
        try:
            if float(quantity) < 0 or float(price) < 0:
                raise ValueError
        except ValueError:
            return form_error('Quantity and price must be valid positive numbers.')
        rows.append(material_required(
            PROJECT=p, MATERIAL=material_map[material_id], category=category.strip(),
            quantity=quantity, price=price,
        ))
    if not rows:
        return form_error('Add at least one material row.')
    material_required.objects.bulk_create(rows)
    messages.success(request, f'{len(rows)} material requirement(s) added successfully.')
    return redirect('View_materials_required', id=pid)

@legacy_role_required('Project Manager')
def Add_material(request):
    return render(request,'Project Manager/Add Materials.html')

@require_POST
@legacy_role_required('Project Manager')
@db_transaction.atomic
def Add_material_post(request):
    names=request.POST.getlist('name')
    units=request.POST.getlist('unit')
    form_rows = _posted_rows(request, 'name', 'unit')
    if len(names) != len(units):
        messages.error(request, 'Material row data is incomplete.')
        return render(request, 'Project Manager/Add Materials.html', {'form_rows': form_rows}, status=400)
    rows=[material(name=name.strip(), unit=unit) for name, unit in zip(names, units) if name.strip() and unit]
    if not rows:
        messages.error(request, 'Add at least one material row.')
        return render(request, 'Project Manager/Add Materials.html', {'form_rows': form_rows}, status=400)
    material.objects.bulk_create(rows)
    messages.success(request, f'{len(rows)} material(s) added successfully.')
    return redirect('View_material')

def Add_project_inspection_details(request,id):
    res=project.objects.get(id=id)
    return  render(request,'Project Manager/Add Project Inspection Details.html',{'data':res})

def Add_project_inspection_details_post(request):
    pid=request.POST['pid']
    p=project.objects.get(id=pid)
    d=request.POST['date']
    type=request.POST['type']
    report=request.FILES['report']

    from datetime import datetime
    fs = FileSystemStorage()
    date = datetime.now().strftime("%Y%m%d%H%M%S") + report.name
    fn = fs.save(date, report)

    apidj=inspection()
    apidj.report=fs.url(fn)
    apidj.PROJECT=p
    apidj.date=d
    apidj.type=type
    apidj.save()
    return HttpResponse("<script>alert('Added Successfully');window.location='/WMS/View_project_inspection/"+pid+"#myid'</script>")

def Add_Requirement_Estimate(request,id,pr,m,c):
    res=project.objects.get(id=id)
    return render(request,'Project Manager/Add Requirement Estimate.html',{'data':res,'pr':pr,'m':m,'c':c})

def Add_Requirement_Estimate_post(request):
    pid=request.POST['pid']
    pr=request.POST['pr']
    m=request.POST['m']
    c=request.POST['c']
    p=project.objects.get(pk=pid)
    est=request.POST['est']
    from datetime import datetime

    amrj=estimate.objects.filter(PROJECT=p, est_no=est)
    if amrj.exists():
        amr=amrj.first()
        # amr.est_no=est
        # amr.PROJECT=p
        # amr.date=datetime.now().strftime("%Y-%m-%d")
        # amr.save()
        request.session['eid']=amr.id
        id= request.session['eid']
    else:
        amrj=estimate()
        amrj.est_no = est
        amrj.PROJECT = p
        amrj.date = datetime.now().strftime("%Y-%m-%d")
        amrj.save()
        request.session['eid'] = amrj.id
        id = request.session['eid']
    return HttpResponse("<script>alert('Added Successfully');window.location='/WMS/Draft_Requirement_budget/"+str(id)+"/"+str(pr)+"/"+str(m)+"/"+str(c)+"'</script>")

def Add_Subcontractor_Estimate(request,id,amount):
    res=project.objects.get(id=id)
    return render(request,'Project Manager/Add Subcontractor Estimate.html',{'data':res,'amount':amount})

def Add_Subcontractor_Estimate_post(request):
    pid=request.POST['pid']
    amount=request.POST['amount']
    p=project.objects.get(pk=pid)
    est=request.POST['est']
    from datetime import datetime

    amrj=estimate.objects.filter(PROJECT=p, est_no=est)
    if amrj.exists():
        amr=amrj.first()
        request.session['eid']=amr.id
        id= request.session['eid']
    else:
        amrj=estimate()
        amrj.est_no = est
        amrj.PROJECT = p
        amrj.date = datetime.now().strftime("%Y-%m-%d")
        amrj.save()
        request.session['eid'] = amrj.id
        id = request.session['eid']
    return HttpResponse("<script>alert('Added Successfully');window.location='/WMS/Draft_Subcontractor_budget/"+str(id)+"/"+str(amount)+"'</script>")

def Add_Subcontractor_schedule(request,id):
    p=subcotractor_project_allocation.objects.get(id=id)
    return render(request,'Project Manager/Add Subcontractor Schedule.html',{'data':p,'id':id})

def Add_Subcontractor_schedule_post(request):
    id=request.POST['id']
    pid=request.POST['pid']
    sp=subcotractor_project_allocation.objects.get(id=pid)
    from_date=request.POST['from']
    to_date=request.POST['to']

    assj=subcontractor_schedule()
    assj.SUBCONTRACTOR_PROJECT_ALLOCATION=sp
    assj.from_date=from_date
    assj.to_date=to_date
    assj.save()
    return HttpResponse("<script>alert('Added Successfully');window.location='/WMS/Add_Subcontractor_schedule/"+id+"'</script>")

def Add_Subcontractor_to_project(request,id):
    p=project.objects.get(id=id)
    s=subcontractor.objects.all()
    w=work.objects.filter(PROJECT=id)
    return render(request,'Project Manager/Add Subcontractor to project.html',{'data':p,'data1':s,'data2':w,'id':id})

def Add_Subcontractor_to_project_post(request):
    request.POST['id']
    pid=request.POST['p']
    p=project.objects.get(pk=pid)
    sub=request.POST['sub']
    s=subcontractor.objects.get(pk=sub)
    wrk=request.POST['wk']
    wk=work.objects.get(pk=wrk)
    amount=request.POST['amount']

    aspj=subcotractor_project_allocation()
    aspj.PROJECT=p
    aspj.SUBCONTRACTOR=s
    aspj.WORK=wk
    aspj.amount=amount
    aspj.save()
    return HttpResponse("<script>alert('Added Successfully');window.location='/WMS/Add_Subcontractor_Estimate/"+pid+"/"+amount+"#myid'</script>")

def Add_Subcontractor(request):
    return render(request,'Project Manager/Add Subcontractor.html')

def Add_Subcontractor_post(request):
    name = request.POST['name']
    phone=request.POST['phone']
    email=request.POST['email']
    place=request.POST['place']
    # category = request.POST['category']

    asj=subcontractor()
    asj.name=name
    asj.phone=phone
    asj.email=email
    asj.place=place
    # asj.work_category=category
    asj.save()
    return HttpResponse("<script>alert('Added Successfully');window.location='/WMS/Add_Subcontractor/'</script>")

@legacy_role_required('Project Manager')
def Add_work_schedule(request,id):
    p=project.objects.get(pk=id)
    unscheduled_work = work.objects.filter(
        PROJECT=id, schedule__isnull=True
    ).only('id', 'category', 'workname').order_by('category', 'workname')
    return render(request,'Project Manager/Add Work Schedule.html',{'data':p,'data1':unscheduled_work,'id':id})

@require_POST
@legacy_role_required('Project Manager')
@db_transaction.atomic
def Add_work_schedule_post(request):
    id=request.POST['id']
    pid=request.POST['pid']
    p=project.objects.get(id=pid)
    work_ids=request.POST.getlist('work')
    starts=request.POST.getlist('start')
    ends=request.POST.getlist('end')
    unscheduled_work = list(work.objects.filter(
        PROJECT=p, schedule__isnull=True
    ).only('id', 'category', 'workname').order_by('category', 'workname'))

    def schedule_error(message):
        submitted = {
            str(work_id): (start, end)
            for work_id, start, end in zip_longest(work_ids, starts, ends, fillvalue='')
        }
        for item in unscheduled_work:
            item.submitted_start, item.submitted_end = submitted.get(str(item.pk), ('', ''))
        messages.error(request, message)
        return render(request, 'Project Manager/Add Work Schedule.html', {
            'data': p, 'data1': unscheduled_work, 'id': id,
        }, status=400)

    if not work_ids or not (len(work_ids) == len(starts) == len(ends)):
        return schedule_error('Schedule row data is incomplete.')
    try:
        normalized_work_ids=[int(value) for value in work_ids]
    except (TypeError, ValueError):
        return schedule_error('Every schedule row must reference a valid scope item.')
    if len(normalized_work_ids) != len(set(normalized_work_ids)):
        return schedule_error('Each scope item can only appear once.')
    work_map=work.objects.filter(
        PROJECT=p, pk__in=normalized_work_ids, schedule__isnull=True
    ).in_bulk()
    if len(work_map) != len(set(normalized_work_ids)):
        return schedule_error('A scope item is invalid or already scheduled.')
    schedule_rows=[]
    from datetime import date, datetime
    progress_rows=[]
    for work_id, start_date, end_date in zip(normalized_work_ids, starts, ends):
        if not start_date or not end_date:
            return schedule_error('Start and end dates are required for every scope item.')
        try:
            parsed_start = date.fromisoformat(start_date)
            parsed_end = date.fromisoformat(end_date)
        except ValueError:
            return schedule_error('Every schedule row requires valid dates.')
        if parsed_end < parsed_start:
            return schedule_error('End date cannot precede start date.')
        scope_item=work_map[work_id]
        schedule_rows.append(schedule(
            PROJECT=p, WORK=scope_item, from_date=parsed_start, to_date=parsed_end
        ))
        progress_rows.append(work_progress(
            WORK=scope_item, PROJECT=p, date=datetime.now().strftime("%Y-%m-%d"),
            status='pending', progress='0',
        ))
    schedule.objects.bulk_create(schedule_rows)
    work_progress.objects.bulk_create(progress_rows)
    messages.success(request, f'{len(schedule_rows)} scope schedule(s) added successfully.')
    return redirect('View_work_schedules', id=id)

@legacy_role_required('Project Manager')
def Add_works(request,id):
    res=project.objects.get(id=id)
    source_projects = project.objects.exclude(id=id).only('id', 'project_no', 'project_name').order_by('project_name')
    return render(request,'Project Manager/Add Works.html',{
        'data':res, 'id':id, 'source_projects':source_projects,
    })

@require_POST
@legacy_role_required('Project Manager')
@db_transaction.atomic
def Add_works_post(request):
    id=request.POST['id']
    pid=request.POST['pid']
    p=project.objects.get(pk=pid)
    categories=request.POST.getlist('category')
    work_names=request.POST.getlist('work')
    form_rows = _posted_rows(request, 'category', 'work')

    def form_error(message):
        messages.error(request, message)
        return render(request, 'Project Manager/Add Works.html', {
            'data': p, 'id': id,
            'source_projects': project.objects.exclude(id=p.pk).only('id', 'project_no', 'project_name').order_by('project_name'),
            'form_rows': form_rows,
        }, status=400)

    if len(categories) != len(work_names):
        return form_error('Scope row data is incomplete.')
    work_rows=[]
    for category, work_name in zip(categories, work_names):
        category=category.strip()
        work_name=work_name.strip()
        if not category or not work_name:
            return form_error('Every scope row requires a category and description.')
        work_rows.append(work(PROJECT=p, category=category, workname=work_name))
    if not work_rows:
        return form_error('Add at least one scope row.')
    work.objects.bulk_create(work_rows)
    messages.success(request, f'{len(work_rows)} scope item(s) added successfully.')
    return redirect('View_work', id=id)


@legacy_role_required('Project Manager')
def Project_list_data(request, id, data_type):
    """Return existing planning rows so the bulk forms can import and edit them."""
    source = project.objects.filter(pk=id).first()
    if not source or data_type not in ('scope', 'materials'):
        return JsonResponse({'error': 'Project or list type not found'}, status=404)
    if data_type == 'materials':
        rows = material_required.objects.filter(PROJECT=source).select_related('MATERIAL').order_by('id')
        return JsonResponse({'rows': [{
            'category': item.category, 'material_id': item.MATERIAL_id,
            'material_name': item.MATERIAL.name, 'unit': item.MATERIAL.unit,
            'quantity': item.quantity, 'price': item.price,
        } for item in rows]})
    scope_rows = list(work.objects.filter(PROJECT=source).order_by('id'))
    return JsonResponse({'rows': [{
        'category': item.category, 'work': item.workname,
    } for item in scope_rows]})


def _boq_session_key(project_id):
    return f'boq_planning_{project_id}'


def _planning_project(request, project_id):
    """Resolve a planning project while respecting the legacy allocation model."""
    selected = get_object_or_404(project, pk=project_id)
    if request.session.get('role') == 'Operation Manager':
        return selected
    if not project_manager_allocation.objects.filter(
        PROJECT=selected, STAFF_id=request.session.get('sid')
    ).exists():
        return None
    return selected


def _boq_context(request, selected):
    draft = request.session.get(_boq_session_key(selected.pk), {})
    rows = draft.get('rows', [])
    materials = list(material.objects.all().order_by('name'))
    for row in rows:
        suggestion = suggest_material(row['description'], materials)
        row['suggested_material_id'] = suggestion.id if suggestion else ''
        row['suggested_material_name'] = suggestion.name if suggestion else ''
    return {
        'data': selected,
        'draft': draft,
        'boq_rows': rows,
        'work_packages': build_work_packages(rows) if rows else [],
        'materials': materials,
    }


@legacy_role_required('Project Manager')
def BOQ_planning(request, id):
    selected = _planning_project(request, id)
    if selected is None:
        return HttpResponse('You are not allocated to this project.', status=403)
    return render(request, 'Project Manager/BOQ Planning.html', _boq_context(request, selected))


@require_POST
@legacy_role_required('Project Manager')
def BOQ_import(request, id):
    selected = _planning_project(request, id)
    if selected is None:
        return HttpResponse('You are not allocated to this project.', status=403)
    upload = request.FILES.get('boq_file')
    source_type = request.POST.get('source_type', 'boq')
    if source_type not in ('boq', 'drawing'):
        source_type = 'boq'
    if not upload:
        messages.error(request, 'Select an Excel or CSV file to continue.')
        return redirect('BOQ_planning', id=selected.pk)
    if upload.size > 10 * 1024 * 1024:
        messages.error(request, 'The uploaded file must not exceed 10 MB.')
        return redirect('BOQ_planning', id=selected.pk)
    try:
        rows = parse_boq_upload(upload)
    except BOQImportError as exc:
        messages.error(request, str(exc))
        return redirect('BOQ_planning', id=selected.pk)
    request.session[_boq_session_key(selected.pk)] = {
        'rows': rows,
        'source_type': source_type,
        'source_name': upload.name[:180],
    }
    request.session.modified = True
    label = 'drawing measurement schedule' if source_type == 'drawing' else 'BOQ'
    messages.success(request, f'{len(rows)} measurable row(s) imported from the {label}. Review them before saving.')
    return redirect('BOQ_planning', id=selected.pk)


@require_POST
@legacy_role_required('Project Manager')
def BOQ_clear(request, id):
    selected = _planning_project(request, id)
    if selected is None:
        return HttpResponse('You are not allocated to this project.', status=403)
    request.session.pop(_boq_session_key(selected.pk), None)
    request.session.modified = True
    messages.success(request, 'The imported planning draft was cleared. No project data was changed.')
    return redirect('BOQ_planning', id=selected.pk)


@require_POST
@legacy_role_required('Project Manager')
@db_transaction.atomic
def BOQ_save_materials(request, id):
    selected = _planning_project(request, id)
    if selected is None:
        return HttpResponse('You are not allocated to this project.', status=403)
    draft = request.session.get(_boq_session_key(selected.pk), {})
    rows = draft.get('rows', [])
    if not rows:
        messages.error(request, 'Import a BOQ before preparing the material list.')
        return redirect('BOQ_planning', id=selected.pk)

    selected_indices = {int(value) for value in request.POST.getlist('include_row') if value.isdigit()}
    material_ids = request.POST.getlist('material_id')
    names = request.POST.getlist('new_material_name')
    units = request.POST.getlist('material_unit')
    quantities = request.POST.getlist('material_quantity')
    prices = request.POST.getlist('material_price')
    if not all(len(values) == len(rows) for values in (material_ids, names, units, quantities, prices)):
        messages.error(request, 'Material review data is incomplete. Please review the rows again.')
        return redirect('BOQ_planning', id=selected.pk)

    validated = []
    for index, source in enumerate(rows):
        if index not in selected_indices:
            continue
        material_id = material_ids[index]
        chosen = material.objects.filter(pk=material_id).first() if material_id else None
        new_name = names[index].strip()[:40]
        unit = units[index].strip()[:40]
        if chosen is None:
            if not new_name or not unit:
                messages.error(request, f'Row {index + 1}: select a material or provide a new material name and unit.')
                return redirect('BOQ_planning', id=selected.pk)
        try:
            quantity = float(quantities[index])
            price = float(prices[index] or 0)
            if quantity < 0 or price < 0:
                raise ValueError
        except ValueError:
            messages.error(request, f'Row {index + 1}: material quantity and price must be valid non-negative numbers.')
            return redirect('BOQ_planning', id=selected.pk)
        validated.append((source, chosen, new_name, unit, quantity, price))
    if not validated:
        messages.error(request, 'Select at least one row for the material list.')
        return redirect('BOQ_planning', id=selected.pk)

    created = []
    for source, chosen, new_name, unit, quantity, price in validated:
        if chosen is None:
            chosen = material.objects.filter(name__iexact=new_name).first()
            if chosen is None:
                chosen = material.objects.create(name=new_name, unit=unit)
        created.append(material_required(
            PROJECT=selected,
            MATERIAL=chosen,
            category=source['category'][:40],
            quantity=f'{quantity:g}',
            price=f'{price:g}',
        ))
    material_required.objects.bulk_create(created)
    messages.success(request, f'{len(created)} reviewed material requirement(s) added to the project.')
    return redirect('View_materials_required', id=selected.pk)


def _posted_work_packages(request):
    fields = ('package_title', 'package_scope', 'package_preparation', 'package_procedure',
              'package_quality', 'package_safety', 'package_completion')
    columns = [request.POST.getlist(field) for field in fields]
    if not columns or any(len(column) != len(columns[0]) for column in columns):
        return []
    return [dict(zip((field.removeprefix('package_') for field in fields), values))
            for values in zip(*columns)]


@require_POST
@legacy_role_required('Project Manager')
@db_transaction.atomic
def BOQ_save_work_order(request, id):
    selected = _planning_project(request, id)
    if selected is None:
        return HttpResponse('You are not allocated to this project.', status=403)
    packages = _posted_work_packages(request)
    if not packages:
        messages.error(request, 'No reviewed work-order packages were submitted.')
        return redirect('BOQ_planning', id=selected.pk)
    for package in packages:
        title = package['title'].strip()
        scope = package['scope'].strip()
        if not title or not scope:
            messages.error(request, 'Every work package requires a title and scope.')
            return redirect('BOQ_planning', id=selected.pk)
    created = 0
    for package in packages:
        title = package['title'].strip()
        scope = package['scope'].strip()
        work_name = scope.split(';', 1)[0].strip()[:40] or title[:40]
        if not work.objects.filter(
            PROJECT=selected, category=title[:40], workname=work_name
        ).exists():
            work.objects.create(PROJECT=selected, category=title[:40], workname=work_name)
            created += 1
    request.session[f'work_order_{selected.pk}'] = packages
    request.session.modified = True
    messages.success(request, f'Work order reviewed. {created} new scope item(s) added; the method statement is ready to download.')
    return redirect('BOQ_planning', id=selected.pk)


@require_GET
@legacy_role_required('Project Manager')
def BOQ_work_order_pdf(request, id):
    selected = _planning_project(request, id)
    if selected is None:
        return HttpResponse('You are not allocated to this project.', status=403)
    packages = request.session.get(f'work_order_{selected.pk}')
    if not packages:
        rows = request.session.get(_boq_session_key(selected.pk), {}).get('rows', [])
        packages = build_work_packages(rows) if rows else []
    if not packages:
        messages.error(request, 'Import a BOQ before downloading the work order.')
        return redirect('BOQ_planning', id=selected.pk)

    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    output = BytesIO()
    document = SimpleDocTemplate(output, pagesize=A4, rightMargin=18 * mm, leftMargin=18 * mm,
                                 topMargin=16 * mm, bottomMargin=16 * mm)
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name='DocumentTitle', parent=styles['Title'], fontName='Helvetica-Bold',
                              fontSize=16, textColor=colors.HexColor('#012970'), alignment=TA_CENTER))
    story = [Paragraph('WORK ORDER & METHOD STATEMENT', styles['DocumentTitle']), Spacer(1, 5 * mm)]
    project_table = Table([
        ['Project', selected.project_name], ['Project No.', selected.project_no],
        ['Client', selected.client_name], ['Prepared from', 'Reviewed BOQ / measurement schedule'],
    ], colWidths=[35 * mm, 125 * mm])
    project_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'), ('FONTNAME', (1, 0), (1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 9), ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#d9e2f3')),
        ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#f6f9ff')), ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('PADDING', (0, 0), (-1, -1), 6),
    ]))
    story.extend([project_table, Spacer(1, 7 * mm)])
    labels = (('scope', 'Scope'), ('preparation', 'Preparation'), ('procedure', 'Method / Sequence'),
              ('quality', 'Quality Control'), ('safety', 'Health, Safety & Environment'),
              ('completion', 'Completion & Handover'))
    for index, package in enumerate(packages, start=1):
        if index > 1:
            story.append(PageBreak())
        story.append(Paragraph(f"{index}. {package['title']}", styles['Heading2']))
        for key, label in labels:
            story.append(Paragraph(label, styles['Heading4']))
            story.append(Paragraph(package.get(key, '').replace('\n', '<br/>'), styles['BodyText']))
            story.append(Spacer(1, 2 * mm))
    def decorate_page(canvas, doc):
        canvas.saveState()
        canvas.setStrokeColor(colors.HexColor('#d9e2f3'))
        canvas.line(18 * mm, 12 * mm, A4[0] - 18 * mm, 12 * mm)
        canvas.setFont('Helvetica', 8)
        canvas.setFillColor(colors.HexColor('#6c757d'))
        canvas.drawString(18 * mm, 8 * mm, f'{selected.project_no} - Work Order & Method Statement')
        canvas.drawRightString(A4[0] - 18 * mm, 8 * mm, f'Page {doc.page}')
        canvas.restoreState()

    document.build(story, onFirstPage=decorate_page, onLaterPages=decorate_page)
    response = HttpResponse(output.getvalue(), content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{selected.project_no}-work-order-method-statement.pdf"'
    return response


@require_GET
@legacy_role_required('Project Manager')
def BOQ_template(request):
    template_path = settings.BASE_DIR / 'MyApp' / 'boq_templates' / 'WMS-BOQ-measurement-template.xlsx'
    return FileResponse(
        template_path.open('rb'),
        as_attachment=True,
        filename='WMS-BOQ-measurement-template.xlsx',
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )

def Change_password(request):
    return render(request,'Project Manager/Change Password.html')

def Change_password_post(request):
    return _change_session_password(request, '/WMS/Change_password/')

def Draft_budget(request,id):
    res=estimate.objects.filter(id=id)
    res2=budget_estimate.objects.filter(ESTIMATE=id)
    return render(request,'Project Manager/Draft Budget.html',{'data':res,'data1':res2,'id':id})

def Draft_budget_post(request):
    eid = request.session['eid']
    if request.POST:
        e=estimate.objects.get(pk=eid)
        id=request.POST['id']
        wrk=request.POST['wrk']
        category=request.POST['category']
        mcost=request.POST['materialcost']
        if mcost == "":
            mcost = "0"
        lcost = request.POST['labourcost']
        if lcost == "":
            lcost = "0"
        vcost = request.POST['vehiclecost']
        if vcost == "":
            vcost = "0"
        subcost = request.POST['subcontractorcost']
        if subcost == "":
            subcost = "0"
        otherexpenses = request.POST['otherexpenses']
        if otherexpenses == "":
            otherexpenses = "0"
        total=float(mcost)+float(lcost)+float(vcost)+float(subcost)+float(otherexpenses)

        dbj=budget_estimate()
        dbj.ESTIMATE=e
        dbj.work=wrk
        dbj.work_category=category
        dbj.material_cost=mcost
        dbj.labour_cost=lcost
        dbj.vehicle_cost=vcost
        dbj.subcontractor_cost=subcost
        dbj.other_expenses=otherexpenses
        dbj.total=total
        dbj.save()

    estimate.objects.filter(id=eid)
    res2 = budget_estimate.objects.filter(ESTIMATE=eid)
    # res = budget_estimate.objects.filter(ESTIMATE=eid)
    tt = 0
    for i in res2:
        tt = float(tt)+float(i.total)
    # return HttpResponse("<script>alert('Added Succesfully');window.location='/WMS/Draft_budget/"+id+"'</script>")
    return render(request,'Project Manager/Draft Budget.html',{'data1':res2,'id':id,'tt':tt})

def Exit_budget(request):
    return redirect('/WMS/View_Ongoing_projects_pm')

def Draft_Requirement_budget(request,id,pr,m,c):
    res=estimate.objects.filter(id=id)
    res2=budget_estimate.objects.filter(ESTIMATE=id)
    return render(request,'Project Manager/Draft Requirement Budget.html',{'data':res,'data1':res2,'id':id,'pr':pr,'m':m,'c':c})

def Draft_Requirement_budget_post(request):
    eid = request.session['eid']
    if request.POST:
        e=estimate.objects.get(pk=eid)
        id=request.POST['id']
        wrk=request.POST['wrk']
        category=request.POST['category']
        mcost=request.POST['materialcost']
        if mcost == "":
            mcost = "0"
        lcost = request.POST['labourcost']
        if lcost == "":
            lcost = "0"
        vcost = request.POST['vehiclecost']
        if vcost == "":
            vcost = "0"
        subcost = request.POST['subcontractorcost']
        if subcost == "":
            subcost = "0"
        otherexpenses = request.POST['otherexpenses']
        if otherexpenses == "":
            otherexpenses = "0"
        total=float(mcost)+float(lcost)+float(vcost)+float(subcost)+float(otherexpenses)

        dbj=budget_estimate()
        dbj.ESTIMATE=e
        dbj.work=wrk
        dbj.work_category=category
        dbj.material_cost=mcost
        dbj.labour_cost=lcost
        dbj.vehicle_cost=vcost
        dbj.subcontractor_cost=subcost
        dbj.other_expenses=otherexpenses
        dbj.total=total
        dbj.save()

    res = budget_estimate.objects.filter(ESTIMATE=eid)
    tt = 0
    for i in res:
        tt = float(tt)+float(i.total)
    # return HttpResponse("<script>alert('Added Succesfully');window.location='/WMS/Draft_budget/"+id+"'</script>")
    return render(request,'Project Manager/Draft Budget.html',{'data1':res,'id':id,'tt':tt})

def Draft_Subcontractor_budget(request,id,amnt):
    res=estimate.objects.filter(id=id)
    res2=budget_estimate.objects.filter(ESTIMATE=id)
    return render(request,'Project Manager/Draft Subcontractor Budget.html',{'data':res,'data1':res2,'id':id,'amnt':amnt})

def Draft_Subcontractor_budget_post(request):
    eid = request.session['eid']
    if request.POST:
        e=estimate.objects.get(pk=eid)
        id=request.POST['id']
        wrk=request.POST['wrk']
        category=request.POST['category']
        mcost=request.POST['materialcost']
        if mcost == "":
            mcost = "0"
        lcost = request.POST['labourcost']
        if lcost == "":
            lcost = "0"
        vcost = request.POST['vehiclecost']
        if vcost == "":
            vcost = "0"
        subcost = request.POST['subcontractorcost']
        if subcost == "":
            subcost = "0"
        otherexpenses = request.POST['otherexpenses']
        if otherexpenses == "":
            otherexpenses = "0"
        total=float(mcost)+float(lcost)+float(vcost)+float(subcost)+float(otherexpenses)

        dbj=budget_estimate()
        dbj.ESTIMATE=e
        dbj.work=wrk
        dbj.work_category=category
        dbj.material_cost=mcost
        dbj.labour_cost=lcost
        dbj.vehicle_cost=vcost
        dbj.subcontractor_cost=subcost
        dbj.other_expenses=otherexpenses
        dbj.total=total
        dbj.save()

    res = budget_estimate.objects.filter(ESTIMATE=eid)
    tt = 0
    for i in res:
        tt = float(tt)+float(i.total)
    # return HttpResponse("<script>alert('Added Succesfully');window.location='/WMS/Draft_budget/"+id+"'</script>")
    return render(request,'Project Manager/Draft Budget.html',{'data1':res,'id':id,'tt':tt})

def Edit_budget(request,id,pid):
    e=budget_estimate.objects.get(id=id)
    return render(request,'Project Manager/Edit Budget.html',{'data':e,'pid':pid})

def Edit_budget_post(request):
    pid=request.POST['pid']
    bid=request.POST['bid']
    category=request.POST['category']
    work=request.POST['work']
    mcost=request.POST['materialcost']
    if mcost=="":
        mcost="0"
    lcost=request.POST['labourcost']
    if lcost=="":
        lcost="0"
    vcost=request.POST['vehiclecost']
    if vcost=="":
        vcost="0"
    subcost=request.POST['subcontractorcost']
    if subcost=="":
        subcost="0"
    otherexpenses=request.POST['otherexpenses']
    if otherexpenses=="":
        otherexpenses="0"
    total=float(mcost)+float(lcost)+float(vcost)+float(subcost)+float(otherexpenses)
    budget_estimate.objects.filter(id=bid).update(work_category=category,work=work,material_cost = mcost,labour_cost = lcost,vehicle_cost = vcost,subcontractor_cost = subcost,other_expenses = otherexpenses,total = total)
    return HttpResponse("<script>alert('Edited Succesfully');window.location='/WMS/View_budget/"+pid+"'</script>")

def Delete_budget(request,id,pid):
    budget_estimate.objects.filter(id=id).delete()
    return HttpResponse("<script>alert('Deleted Succesfully');window.location='/WMS/View_budget/"+pid+"'</script>")

def Edit_Estimate(request,id,pid):
    res=estimate.objects.get(id=id)
    return render(request,'Project Manager/Edit Estimate.html',{'data':res,'pid':pid})

def Edit_Estimate_post(request):
    eid=request.POST['eid']
    pid=request.POST['pid']
    est=request.POST['est']

    estimate.objects.filter(id=eid).update(est_no=est)
    # request.session['eid']=amrj.id
    # id= request.session['eid']
    return HttpResponse("<script>alert('Edited Successfully');window.location='/WMS/View_Estimate/"+pid+"#myid'</script>")

def Delete_Estimate(request,id,pid):
    estimate.objects.filter(id=id).delete()
    return HttpResponse("<script>alert('Deleted Succesfully');window.location='/WMS/View_Estimate/"+pid+"#myid'</script>")

def Edit_issued_materials_to_site(request,id,pid):
    e=material_issued.objects.get(id=id)
    s=staff.objects.filter(designation='Supervisor')
    m=material.objects.all()
    return render(request,'Project Manager/Edit Issued Materials to Site.html',{'data':e,'data1':s,'data2':m,'pid':pid})

def Edit_issued_materials_to_site_post(request):
    pid=request.POST['pid']
    mid=request.POST['mid']
    sup=request.POST['supervisor']
    s=staff.objects.get(id=sup)
    mtl=request.POST['material']
    m=material.objects.get(id=mtl)
    quantity=request.POST['quantityissued']

    material_issued.objects.filter(id=mid).update(MATERIAL=m,quantity_issued=quantity,STAFF=s)
    return HttpResponse("<script>alert('Edited Succesfully');window.location='/WMS/View_issued_materials_to_site/"+pid+"#myid'</script>")

def Delete_ismts(request,id,pid):
    material_issued.objects.filter(id=id).delete()
    return HttpResponse("<script>alert('Deleted Succesfully');window.location='/WMS/View_issued_materials_to_site/"+pid+"#myid'</script>")

def Edit_material_required(request,id,pid):
    res=material_required.objects.get(id=id)
    res2=material.objects.all()
    return render(request,'Project Manager/Edit Materials Required.html',{'data':res,'data2':res2,'pid':pid})

def Edit_material_required_post(request):
    pid=request.POST['pid']
    mrid=request.POST['mrid']
    category=request.POST['category']
    material=request.POST['material']
    quantity=request.POST['quantity']
    price=request.POST['price']
    material_required.objects.filter(id=mrid).update(category=category,MATERIAL=material,quantity=quantity,price=price)
    return HttpResponse("<script>alert('Edited Succesfully');window.location='/WMS/View_materials_required/"+pid+"#myid'</script>")

def Delete_materialreqd(request,id,pid):
    material_required.objects.filter(id=id).delete()
    return HttpResponse("<script>alert('Deleted Succesfully');window.location='/WMS/View_materials_required/"+pid+"#myid'</script>")

def Edit_material(request,id):
    res=material.objects.get(id=id)
    return render(request,'Project Manager/Edit Materials.html',{'data':res})

def Edit_material_post(request):
    mid=request.POST['mid']
    name=request.POST['name']
    unit=request.POST['unit']

    material.objects.filter(pk=mid).update(name=name,unit=unit)
    return HttpResponse("<script>alert('Edited Succesfully');window.location='/WMS/View_material/'</script>")

def Delete_material(request,id):
    material.objects.filter(id=id).delete()
    return HttpResponse("<script>alert('Deleted Succesfully');window.location='/WMS/View_material/'</script>")

def Edit_Projec_allocation_to_purchaser(request,id):
    res=staff.objects.filter(designation='Purchaser')
    res1=purchaser_project_allocation.objects.get(pk=id)
    return render(request,'Project Manager/Edit Project allocation to purchaser.html',{'data':res,'data1':res1})

def Edit_Projec_allocation_to_purchaser_post(request):
    pid=request.POST['pid']
    eid=request.POST['eid']
    purchaser=request.POST['purchaser']
    res1=staff.objects.get(pk=purchaser)

    purchaser_project_allocation.objects.filter(pk=eid).update(STAFF=res1)
    return HttpResponse("<script>alert('Edited Succesfully');window.location='/WMS/View_Project_allocated_to_purchaser/"+pid+"#myid'</script>")

def Delete_pcal(request,id,pid):
    purchaser_project_allocation.objects.filter(id=id).delete()
    return HttpResponse("<script>alert('Deleted Succesfully');window.location='/WMS/View_Project_allocated_to_purchaser/"+pid+"#myid'</script>")

def Edit_project_inspection_details(request,id,pid):
    res=inspection.objects.get(id=id)
    return  render(request,'Project Manager/Edit Project Inspection Details.html',{'data':res,'pid':pid})

def Edit_project_inspection_details_post(request):
    project_id=request.POST['project_id']
    inspection_id=request.POST['inspection_id']
    d=request.POST['date']
    type=request.POST['type']
    # report=request.POST['report']
    if 'report' in request.FILES:
        report = request.FILES['report']
        from datetime import datetime
        fs = FileSystemStorage()
        date = datetime.now().strftime("%Y%m%d%H%M%S") + report.name
        saved_name = fs.save(date, report)
        inspection.objects.filter(id=inspection_id, PROJECT_id=project_id).update(
            date=d, type=type, report=fs.url(saved_name)
        )
    else:
        inspection.objects.filter(id=inspection_id, PROJECT_id=project_id).update(date=d,type=type)
    return HttpResponse("<script>alert('Edited Succesfully');window.location='/WMS/View_project_inspection/"+project_id+"#myid'</script>")

def Delete_inspection(request,id,pid):
    inspection.objects.filter(id=id).delete()
    return HttpResponse("<script>alert('Deleted Succesfully');window.location='/WMS/View_project_inspection/"+pid+"#myid'</script>")

def Edit_Subcontractor_to_project(request,id,pid):
    ep=subcotractor_project_allocation.objects.get(id=id)
    s=subcontractor.objects.all()
    w=work.objects.filter(PROJECT=pid)
    return render(request,'Project Manager/Edit Subcontractor of project.html',{'data':ep,'data1':s,'data2':w,'pid':pid})

def Edit_Subcontractor_to_project_post(request):
    id=request.POST['id']
    pid=request.POST['pid']
    sub=request.POST['sub']
    s=subcontractor.objects.get(id=sub)
    wk=request.POST['wk']
    w=work.objects.get(pk=wk)
    subcotractor_project_allocation.objects.filter(id=pid).update(SUBCONTRACTOR=s,WORK=w)
    return HttpResponse("<script>alert('Edited Succesfully');window.location='/WMS/View_Subcontractor_of_project/"+id+"#myid'</script>")

def Delete_subofpr(request,id,pid):
    subcotractor_project_allocation.objects.get(id=id).delete()
    return HttpResponse("<script>alert('Deleted Succesfully');window.location='/WMS/View_Subcontractor_of_project/"+pid+"#myid'</script>")

def Edit_Subcontractor_schedule(request,id,pid):
    ep=subcontractor_schedule.objects.get(id=id)
    return render(request,'Project Manager/Edit Subcontractor Schedule.html',{'data':ep,'pid':pid})

def Edit_Subcontractor_schedule_post(request):
    id=request.POST['pid']
    pid=request.POST['eid']
    from_date=request.POST['from']
    to_date=request.POST['to']

    subcontractor_schedule.objects.filter(id=pid).update(from_date=from_date,to_date=to_date)
    return HttpResponse("<script>alert('Edited Succesfully');window.location='/WMS/View_subcontractor_schedule/"+id+"'</script>")

def Delete_subschd(request,id,pid):
    subcontractor_schedule.objects.filter(id=id).delete()
    return HttpResponse("<script>alert('Deleted Succesfully');window.location='/WMS/View_subcontractor_schedule/"+pid+"'</script>")

def Edit_Subcontractor(request,id):
    res=subcontractor.objects.get(id=id)
    return render(request,'Project Manager/Edit Subcontractor.html',{'data':res})

def Edit_Subcontractor_post(request):
    sid=request.POST['sid']
    name = request.POST['name']
    phone=request.POST['phone']
    email=request.POST['email']
    place=request.POST['place']
    # category = request.POST['category']

    subcontractor.objects.filter(id=sid).update(name = name,phone = phone,email = email,place = place)
    return HttpResponse("<script>alert('Edited Succesfully');window.location='/WMS/View_subcontractor/'</script>")

def Delete_subcontractor(request,id):
    subcontractor.objects.filter(id=id).delete()
    return HttpResponse("<script>alert('Deleted Succesfully');window.location='/WMS/View_subcontractor/'</script>")

def Edit_Uploaded_documents(request,id,pid):
    e=documents.objects.get(id=id)
    return render(request, 'Project Manager/Edit Uploaded Documents.html',{'data':e,'pid':pid})

def Edit_Uploaded_documents_post(request):
    pid=request.POST['pid']
    did=request.POST['did']
    name=request.POST['name']
    if 'file' in request.FILES:
        file=request.FILES['file']
        from datetime import datetime
        fs=FileSystemStorage()
        d=datetime.now().strftime("%Y%m%d%H%M%S")+file.name
        fn=fs.save(d,file)
        documents.objects.filter(id=did).update(name=name,file=fs.url(fn))
    else:
        documents.objects.filter(id=did).update(name=name)
    return HttpResponse("<script>alert('Edited Succesfully');window.location='/WMS/View_uploaded_document/"+pid+"#myid'</script>")

def Delete_document(request,id,pid):
    documents.objects.filter(id=id).delete()
    return HttpResponse("<script>alert('Deleted Successfully');window.location='/WMS/View_uploaded_document/"+pid+"#myid'</script>")

def Edit_Uploaded_drawings(request,id,pid):
    e=drawing.objects.get(id=id)
    return render(request, 'Project Manager/Edit Uploaded Drawings.html',{'data':e,'pid':pid})

def Edit_Uploaded_drawings_post(request):
    pid=request.POST['pid']
    eid=request.POST['eid']
    file=request.FILES['file']
    from datetime import datetime
    fs=FileSystemStorage()
    date=datetime.now().strftime("%Y%m%d%H%M%S")+file.name
    fn=fs.save(date,file)
    drawing.objects.filter(id=eid).update(file = fs.url(fn))
    return HttpResponse("<script>alert('Edited Succesfully');window.location='/WMS/View_uploaded_drawings/"+pid+"#myid'</script>")

def Delete_drawing(request,id,pid):
    drawing.objects.filter(id=id).delete()
    return HttpResponse("<script>alert('Deleted Succesfully');window.location='/WMS/View_uploaded_drawings/"+pid+"#myid'</script>")

def Edit_work_schedule(request,id,pid):
    e=schedule.objects.get(id=id)
    return render(request,'Project Manager/Edit Work Schedule.html',{'data':e,'pid':pid})

def Edit_work_schedule_post(request):
    pid=request.POST['pid']
    sid=request.POST['sid']
    start_date=request.POST['start']
    end_date=request.POST['end']
    schedule.objects.filter(id=sid).update(from_date = start_date,to_date = end_date)
    return HttpResponse("<script>alert('Edited Succesfully');window.location='/WMS/View_work_schedules/"+pid+"#myid'</script>")

def Delete_wshd(request,id,pid):
    schedule.objects.filter(id=id).delete()
    return HttpResponse("<script>alert('Deleted Succesfully');window.location='/WMS/View_work_schedules/"+pid+"#myid'</script>")

def Edit_works(request,id,pid):
    ed=work.objects.get(id=id)
    return render(request,'Project Manager/Edit Work.html',{'data':ed,'pid':pid})

def Edit_works_post(request):
    pid=request.POST['pid']
    wid=request.POST['wid']
    category=request.POST['category']
    workn=request.POST['work']

    work.objects.filter(pk=wid).update(category = category,workname = workn)
    return HttpResponse("<script>alert('Edited Succesfully');window.location='/WMS/View_work/"+pid+"#myid'</script>")

def Delete_work(request,id,pid):
    work.objects.filter(id=id).delete()
    return HttpResponse("<script>alert('Deleted Succesfully');window.location='/WMS/View_work/"+pid+"#myid'</script>")

def Delete_chatpm(request,id,pid):
    lid=request.session['lid']
    chat.objects.filter(id=id, LOGIN_id=lid).delete()
    p=project.objects.get(id=pid).project_name
    return render(request,'Project Manager/fur_chat.html', {'id':pid,'lid':lid,'p':p})

def chatspm(request,id,msg):
    lid=str(request.session['lid'])
    from datetime import datetime

    sender = staff.objects.get(LOGIN_id=lid)

    d=chat()
    d.LOGIN_id=lid
    d.PROJECT_id=id
    d.message=msg
    d.date=datetime.now().strftime("%Y-%m-%d")
    d.time=datetime.now().strftime("%I:%M %p")
    d.type=sender.name+" , "+sender.designation
    d.save()
    return JsonResponse({'status':'ok'})

def chatpm(request,id):
    lid=request.session['lid']
    p=project.objects.get(id=id).project_name
    return render(request,'Project Manager/fur_chat.html', {'id':id,'lid':lid,'p':p})

def viewmsg_pm(request,id):
    return JsonResponse({'data': _chat_messages(id, request.session['lid'])})

def Issue_materials_to_site(request,id):
    res=project.objects.get(id=id)
    s=staff.objects.filter(designation='Supervisor')
    m=material.objects.all()
    return render(request,'Project Manager/Issue Materials to Site.html',{'data':res,'data2':s,'data3':m,'id':id})

def Issue_materials_to_site_post(request):
    id=request.POST['id']
    pid=request.POST['pid']
    p=project.objects.get(id=pid)
    sup=request.POST['supervisor']
    s=staff.objects.get(id=sup)
    mat=request.POST['material']
    m=material.objects.get(id=mat)
    quantity_issued=request.POST['quantity_issued']
    # unit=request.POST['unit']
    from datetime import datetime
    d=datetime.now().strftime("%Y-%m-%d")

    imj = material_issued()
    imj.date=d
    imj.PROJECT=p
    imj.MATERIAL = m
    imj.quantity_issued = quantity_issued
    # imj.unit = unit
    imj.STAFF = s
    imj.status="issued"
    imj.save()
    return HttpResponse("<script>alert('Added Succesfully');window.location='/WMS/View_issued_materials_to_site/"+id+"#myid'</script>")

def Projec_allocation_to_purchaser(request,id):
    res=staff.objects.filter(designation='Purchaser')
    res1=project.objects.get(pk=id)
    return render(request,'Project Manager/Project allocation to purchaser.html',{'data':res,'data1':res1})

def Projec_allocation_to_purchaser_post(request):
    pid=request.POST['pid']
    res=project.objects.get(pk=pid)
    purchaser=request.POST['purchaser']
    res1=staff.objects.get(pk=purchaser)
    from datetime import datetime
    pm=purchaser_project_allocation()
    pm.PROJECT=res
    pm.STAFF=res1
    pm.allocated_date=datetime.now().strftime("%Y-%m-%d")
    pm.save()
    return HttpResponse("<script>alert('Allocated Purchaser');window.location='/WMS/View_Project_allocated_to_purchaser/"+pid+"#myid'</script>")

def Upload_documents(request,id):
    res=project.objects.get(id=id)
    return render(request, 'Project Manager/Upload Documents.html',{'data':res,'id':id})

def Upload_documents_post(request):
    id=request.POST['id']
    pid=request.POST['pid']
    p=project.objects.get(id=pid)
    n=request.POST['name']
    f=request.FILES['file']
    from datetime import datetime
    fs=FileSystemStorage()
    d=datetime.now().strftime("%Y%m%d%H%M%S") + f.name
    fn=fs.save(d,f)
    date=datetime.now().strftime("%Y-%m-%d")

    euj = documents()
    euj.name = n
    euj.date=date
    euj.PROJECT=p
    euj.file =fs.url(fn)
    euj.save()
    return HttpResponse("<script>alert('Added Succesfully');window.location='/WMS/View_uploaded_document/"+id+"#myid'</script>")

def Upload_drawings(request,id):
    res=project.objects.get(id=id)
    return render(request, 'Project Manager/Upload Drawings.html',{'data':res,'id':id})

def Upload_drawings_post(request):
    id=request.POST['id']
    pid=request.POST['pid']
    p=project.objects.get(id=pid)
    f=request.FILES['file']
    from datetime import datetime
    fs=FileSystemStorage()
    d=datetime.now().strftime("%Y%m%d%H%M%S")+f.name
    fn=fs.save(d,f)
    date=datetime.now().strftime("%Y-%m-%d")

    euj = drawing()
    euj.PROJECT=p
    euj.file = fs.url(fn)
    euj.date=date
    euj.save()
    return HttpResponse("<script>alert('Added Succesfully');window.location='/WMS/View_uploaded_drawings/"+id+"#myid'</script>")

def View_assigned_projects(request):
    res=project_manager_allocation.objects.filter(STAFF=request.session["sid"])
    return render(request, 'Project Manager/View Assigned Projects.html',{'data':res})

def search_aspp(request):
    button=request.POST['button']
    if button == 'Search':
        txt=request.POST['text']
        res = project_manager_allocation.objects.filter(STAFF=request.session["sid"],PROJECT__project_name__icontains=txt)
        return render(request, 'Project Manager/View Assigned Projects.html', {'data': res})
    else:
        frm=request.POST['from']
        to=request.POST['to']
        res = project_manager_allocation.objects.filter(STAFF=request.session["sid"],PROJECT__date__range=[frm,to])
        return render(request, 'Project Manager/View Assigned Projects.html', {'data': res})

def View_completed_projectspm(request):
    res=project_manager_allocation.objects.filter(STAFF=request.session["sid"],PROJECT__status='Completed')
    return render(request, 'Project Manager/View Completed Projects.html',{'data':res})

def search_aspcppm(request):
    button=request.POST['button']
    if button == 'Search':
        txt=request.POST['text']
        res = project_manager_allocation.objects.filter(STAFF=request.session["sid"],PROJECT__status='completed',PROJECT__project_name__icontains=txt)
        return render(request, 'Project Manager/View Completed Projects.html', {'data': res})
    else:
        frm=request.POST['from']
        to=request.POST['to']
        res = project_manager_allocation.objects.filter(STAFF=request.session["sid"],PROJECT__status='completed',PROJECT__date__range=[frm,to])
        return render(request, 'Project Manager/View Completed Projects.html', {'data': res})

def View_budget(request,id):
    res=budget_estimate.objects.filter(ESTIMATE=id)
    return render(request, 'Project Manager/View Budget.html',{'data':res,'id':id})

def search_bgtpm(request):
    id = request.POST['id']
    c=request.POST['textfield']
    res = budget_estimate.objects.filter(work_category__icontains=c,ESTIMATE=id)
    return render(request, 'Project Manager/View Budget.html', {'data': res, 'id': id})

def View_Estimate(request,id):
    res=estimate.objects.filter(PROJECT=id)
    tt=[]
    for i in res:
        j=budget_estimate.objects.filter(ESTIMATE_id=i.id)
        myval=0
        for k in j:
            myval+=float(k.total)
        tt.append({"id":i.id,"date":i.date,"est_no":i.est_no,"PROJECT":i.PROJECT.id,"my":myval})
    res2 = project_manager_allocation.objects.get(PROJECT=id, STAFF=request.session["sid"], PROJECT__status='ongoing')
    return render(request, 'Project Manager/View Estimate.html',{'data':res2,'data1':tt,'id':id})

def search_est(request):
    id = request.POST['pid']
    p = project.objects.get(pk=id)
    frm = request.POST['from']
    to = request.POST['to']
    res = estimate.objects.filter(PROJECT=p,date__range=[frm,to])
    tt = []
    for i in res:
        j = budget_estimate.objects.filter(ESTIMATE_id=i.id)
        myval = 0
        for k in j:
            myval += float(k.total)
        tt.append({"id": i.id, "date": i.date, "est_no": i.est_no, "PROJECT": i.PROJECT.id, "my": myval})
    res2 = project_manager_allocation.objects.get(PROJECT=id, STAFF=request.session["sid"], PROJECT__status='ongoing')
    return render(request, 'Project Manager/View Estimate.html', {'data': res2,'data1':tt,'id':id})

def View_issued_materials_to_site(request,id):
    res=material_issued.objects.filter(PROJECT=id)
    res2 = project_manager_allocation.objects.get(PROJECT=id, STAFF=request.session["sid"], PROJECT__status='ongoing')
    return render(request, 'Project Manager/View Issued Materials to Site.html',{'data':res2,'data1':res,'id':id})

def search_msd(request):
    button = request.POST['button']
    if button == 'Search':
        id = request.POST['pid']
        p = project.objects.get(pk=id)
        txt = request.POST['text']
        res = material_issued.objects.filter(PROJECT=p,MATERIAL__name__icontains=txt)
        res2 = project_manager_allocation.objects.get(PROJECT=id, STAFF=request.session["sid"],PROJECT__status='ongoing')
        return render(request, 'Project Manager/View Issued Materials to Site.html', {'data': res2,'data1':res, 'id': id})
    else:
        id = request.POST['pid']
        p = project.objects.get(pk=id)
        frm = request.POST['from']
        to = request.POST['to']
        res = material_issued.objects.filter(PROJECT=p,date__range=[frm, to])
        res2 = project_manager_allocation.objects.get(PROJECT=id, STAFF=request.session["sid"],PROJECT__status='ongoing')
        return render(request, 'Project Manager/View Issued Materials to Site.html', {'data': res2,'data1':res, 'id': id})

def View_materials_request(request,id):
    res=material_request.objects.filter(status="approved",PROJECT=id)
    res2 = project_manager_allocation.objects.get(PROJECT=id, STAFF=request.session["sid"], PROJECT__status='ongoing')
    return render(request, 'Project Manager/View Material Request.html',{'data':res2,'data1':res,'id':id})

def search_mrt(request):
    button = request.POST['button']
    if button == 'Search':
        id = request.POST['pid']
        p = project.objects.get(pk=id)
        txt = request.POST['text']
        res = material_request.objects.filter(status="approved",PROJECT=p, MATERIAL__name__icontains=txt)
        res2 = project_manager_allocation.objects.get(PROJECT=id, STAFF=request.session["sid"],PROJECT__status='ongoing')
        return render(request, 'Project Manager/View Material Request.html', {'data': res2,'data1':res, 'id': id})
    else:
        id = request.POST['pid']
        p = project.objects.get(pk=id)
        frm = request.POST['from']
        to = request.POST['to']
        res = material_request.objects.filter(status="approved",PROJECT=p, date__range=[frm, to])
        res2 = project_manager_allocation.objects.get(PROJECT=id, STAFF=request.session["sid"],PROJECT__status='ongoing')
        return render(request, 'Project Manager/View Material Request.html', {'data': res2,'data1':res, 'id': id})

def View_materials_report(request,id):
    res=material_required.objects.filter(PROJECT=id)
    l = []
    for i in res:
        res1=material_issued.objects.filter(PROJECT=id,MATERIAL=i.MATERIAL)
        t_issued=0
        for j in res1:
            t_issued += int(j.quantity_issued)
        t_usage=0
        res2=material_usage.objects.filter(PROJECT=id,MATERIAL=i.MATERIAL)
        for k in res2:
            t_usage += int(k.quantity)
        l.append({"material":i.MATERIAL.name,"required":i.quantity,"issued":t_issued,"usage":t_usage})
    res2 = project_manager_allocation.objects.get(PROJECT=id, STAFF=request.session["sid"], PROJECT__status='ongoing')
    return render(request, 'Project Manager/View Materials Report.html',{'data':res2,'data1':l,'id':id})

def search_msrt(request):
    id = request.POST['id']
    p=project.objects.get(pk=id)
    txt = request.POST['text']
    res = material_required.objects.filter(MATERIAL__name__icontains=txt,PROJECT=p)
    l = []
    for i in res:
        res1 = material_issued.objects.filter(PROJECT=id, MATERIAL=i.MATERIAL)
        t_issued = 0
        for j in res1:
            t_issued += int(j.quantity_issued)
        t_usage = 0
        res2 = material_usage.objects.filter(PROJECT=id, MATERIAL=i.MATERIAL)
        for k in res2:
            t_usage += int(k.quantity)
        l.append({"material": i.MATERIAL.name, "required": i.quantity, "issued": t_issued, "usage": t_usage})
    res2 = project_manager_allocation.objects.get(PROJECT=id, STAFF=request.session["sid"], PROJECT__status='ongoing')
    return render(request, 'Project Manager/View Materials Report.html', {'data': res2,'data1':l, 'id': id})

def View_materials_required(request,id):
    res=material_required.objects.filter(PROJECT=id)
    msum = 0
    for i in res:
        msum = msum + (float(i.quantity) * float(i.price))
    res2 = project_manager_allocation.objects.get(PROJECT=id, STAFF=request.session["sid"], PROJECT__status='ongoing')
    return render(request, 'Project Manager/View Materials Required.html',{'data':res2,'data1':res,'id':id,'msum':msum})

def search_msrd(request):
    id = request.POST['id']
    p=project.objects.get(pk=id)
    txt = request.POST['text']
    res = material_required.objects.filter(MATERIAL__name__icontains=txt,PROJECT=p)
    msum = 0
    for i in res:
        msum = msum + (float(i.quantity) * float(i.MATERIAL.price))
    res2 = project_manager_allocation.objects.get(PROJECT=id, STAFF=request.session["sid"], PROJECT__status='ongoing')
    return render(request, 'Project Manager/View Materials Required.html', {'data': res2,'data1':res, 'id': id,'msum':msum})

def View_material(request):
    res=material.objects.all()
    return render(request, 'Project Manager/View Materials.html',{'data':res})

def search_mts(request):
    t=request.POST['text']
    res = material.objects.filter(name__icontains=t)
    return render(request, 'Project Manager/View Materials.html', {'data': res})

def View_notification(request):
    res1=project_manager_allocation.objects.filter(STAFF=request.session["sid"])
    for i in res1:
        res=notification.objects.filter(PROJECT=i.id)
        res.update(status="viewed")
    return render(request, 'Project Manager/View Notification.html',{'data':res})

def search_ntfn(request):
    button = request.POST['button']
    if button == 'Search':
        txt = request.POST['text']
        res1 = project_manager_allocation.objects.filter(STAFF=request.session["sid"])
        for i in res1:
            res = notification.objects.filter(PROJECT=i.id,type__icontains=txt)
        return render(request, 'Project Manager/View Notification.html', {'data':res})
    else:
        frm = request.POST['from']
        to = request.POST['to']
        res1 = project_manager_allocation.objects.filter(STAFF=request.session["sid"])
        for i in res1:
            res = notification.objects.filter(PROJECT=i.id, date__range=[frm, to])
        return render(request, 'Project Manager/View Notification.html', {'data':res})

def View_Ongoing_projects_pm(request):
    res=project_manager_allocation.objects.filter(STAFF=request.session["sid"],PROJECT__status='ongoing')
    return render(request, 'Project Manager/View Ongoing Project.html',{'data':res})

def search_onp(request):
    button=request.POST['button']
    if button == 'Search':
        txt=request.POST['text']
        res = project_manager_allocation.objects.filter(PROJECT__status='ongoing',STAFF=request.session["sid"],PROJECT__project_name__icontains=txt)
        return render(request, 'Project Manager/View Ongoing Project.html', {'data': res})
    else:
        frm=request.POST['from']
        to=request.POST['to']
        res = project_manager_allocation.objects.filter(PROJECT__status='ongoing',STAFF=request.session["sid"],PROJECT__date__range=[frm,to])
        return render(request, 'Project Manager/View Ongoing Project.html', {'data': res})

def View_projects_functionspm(request,id):
    res = project_manager_allocation.objects.get(PROJECT=id,STAFF=request.session["sid"], PROJECT__status='ongoing')
    return render(request,'Project Manager/View Ongoing Projects Functions.html',{'data':res})

def View_pending_materials_request(request,id):
    res=material_request.objects.filter(status="pending",PROJECT=id)
    return render(request, 'Project Manager/View Pending Material Request.html',{'data':res,'id':id})

def search_pmrt(request):
    button = request.POST['button']
    if button == 'Search':
        id = request.POST['pid']
        p = project.objects.get(pk=id)
        txt = request.POST['text']
        res = material_request.objects.filter(status="pending",PROJECT=p, MATERIAL__name__icontains=txt)
        return render(request, 'Project Manager/View Pending Material Request.html', {'data': res, 'id': id})
    else:
        id = request.POST['pid']
        p = project.objects.get(pk=id)
        frm = request.POST['from']
        to = request.POST['to']
        res = material_request.objects.filter(status="pending",PROJECT=p, date__range=[frm, to])
        return render(request, 'Project Manager/View Pending Material Request.html', {'data': res, 'id': id})

def approve_rqt(request,id,pid):
    material_request.objects.filter(pk=id).update(status='approved')
    return HttpResponse("<script>alert('Approved');window.location='/WMS/View_pending_materials_request/"+pid+"'</script>")

def reject_rqt(request,id,pid):
    material_request.objects.filter(pk=id).update(status='rejected')
    return HttpResponse("<script>alert('Rejected');window.location='/WMS/View_pending_materials_request/"+pid+"'</script>")

def View_profile(request):
    res=staff.objects.get(LOGIN=request.session["lid"])
    return render(request, 'Project Manager/View Profile.html',{'data':res})

def View_Project_allocated_to_purchaser(request,id):
    res=purchaser_project_allocation.objects.filter(PROJECT=id)
    res2 = project_manager_allocation.objects.get(PROJECT=id, STAFF=request.session["sid"], PROJECT__status='ongoing')
    return render(request,'Project Manager/View Project Allocated to Purchaser.html',{'data':res2,'data1':res,'id':id})

def search_pcr(request):
    id = request.POST['pid']
    p = project.objects.get(pk=id)
    w=request.POST['text']
    res = purchaser_project_allocation.objects.filter(PROJECT=p,STAFF__name__icontains=w)
    res2 = project_manager_allocation.objects.get(PROJECT=id, STAFF=request.session["sid"], PROJECT__status='ongoing')
    return render(request, 'Project Manager/View Project Allocated to Purchaser.html', {'data': res2,'data1':res, 'id': id})

def View_project_inspection(request,id):
    res=inspection.objects.filter(PROJECT=id)
    res2 = project_manager_allocation.objects.get(PROJECT=id, STAFF=request.session["sid"], PROJECT__status='ongoing')
    return render(request, 'Project Manager/View Project Inspection.html',{'data':res2,'data1':res,'id':id})

def search_insp(request):
    id = request.POST['pid']
    p = project.objects.get(pk=id)
    frm=request.POST['from']
    to=request.POST['to']
    res = inspection.objects.filter(PROJECT=p,date__range=[frm,to])
    res2 = project_manager_allocation.objects.get(PROJECT=id, STAFF=request.session["sid"], PROJECT__status='ongoing')
    return render(request, 'Project Manager/View Project Inspection.html', {'data': res2,'data1':res, 'id': id})

def View_project_payment_entry(request,id):
    res=payemnt_entry.objects.filter(PROJECT=id)
    res2 = project_manager_allocation.objects.get(PROJECT=id, STAFF=request.session["sid"], PROJECT__status='ongoing')
    return render(request, 'Project Manager/View Project Payment Entry.html',{'data':res2,'data2':res,'id':id})

def search_pmnt(request):
    id=request.POST['pid']
    p = project.objects.get(id=id)
    frm=request.POST['from']
    to=request.POST['to']
    res = payemnt_entry.objects.filter(date__range=[frm,to],PROJECT=p)
    res2 = project_manager_allocation.objects.get(PROJECT=id, STAFF=request.session["sid"], PROJECT__status='ongoing')
    return render(request, 'Project Manager/View Project Payment Entry.html', {'data': res2,'data2':res, 'id': id})

def View_project_status(request,id):
    request.session['projectid']=id
    res=work_progress.objects.filter(PROJECT=id)
    res2 = project_manager_allocation.objects.get(PROJECT=id, STAFF=request.session["sid"], PROJECT__status='ongoing')
    wp = len(res)
    wpc = len(work_progress.objects.filter(status='Completed'))
    c=0
    if(wp==wpc):
        c=1
    else:
        c=0
    l = []
    for i in res:
        ws = schedule.objects.filter(WORK=i.WORK, PROJECT=i.PROJECT)
        if ws.exists():
            a = ws[0].to_date
            import datetime
            to_date = datetime.datetime.strftime(a, '%Y-%m-%d')
            today = datetime.datetime.now().strftime("%Y-%m-%d")
            if to_date > today:
                ss = "ok"
                from datetime import datetime as dt
                res = (dt.strptime(to_date, "%Y-%m-%d") - dt.strptime(today, "%Y-%m-%d")).days
                if res < 3:
                    ss = "not"
                    if i.status == "Completed":
                        ss = "ok"
                else:
                    ss = "ok"
            else:
                if i.status == "Completed":
                    ss = "ok"
                else:
                    ss = "no"

                    nobj = notification.objects.filter(notification__contains=i.WORK.workname,PROJECT=i.PROJECT)
                    if not nobj.exists():
                        nobjj=notification()
                        nobjj.date = datetime.datetime.now().strftime("%Y-%m-%d")
                        nobjj.notification = i.WORK.workname+" "+'not completed'
                        nobjj.PROJECT_id = i.PROJECT_id
                        nobjj.type='Work notification'
                        nobjj.status='pending'
                        nobjj.STAFF_id=res2.STAFF_id
                        nobjj.save()
            l.append({'ss': ss, 'WORK': i.WORK, 'date': i.date, 'status': i.status, 'progress': i.progress,'todate': to_date})
    return render(request, 'Project Manager/View Project Status.html',{'data':res2,'data1':l,'id':id,'c':c})

def completed(request):
    project.objects.filter(id=request.session['projectid']).update(status='Completed')
    return HttpResponse("<script>alert('Status Updated');window.location='/WMS/View_project_status/"+request.session['projectid']+"'</script>")

def search_prstpm(request):
    button=request.POST['button']
    if button == 'Search':
        id = request.POST['pid']
        p = project.objects.get(id=id)
        txt=request.POST['text']
        res = work_progress.objects.filter(PROJECT=p,WORK__workname__icontains=txt)
        res2 = project_manager_allocation.objects.get(PROJECT=id, STAFF=request.session["sid"],
                                                      PROJECT__status='ongoing')
        wp = len(res)
        wpc = len(work_progress.objects.filter(status='Completed'))
        if (wp == wpc):
            pass
        else:
            pass
        l = []
        for i in res:
            ws = schedule.objects.filter(WORK=i.WORK, PROJECT=i.PROJECT)
            if ws.exists():
                a = ws[0].to_date
                import datetime
                to_date = datetime.datetime.strftime(a, '%Y-%m-%d')
                today = datetime.datetime.now().strftime("%Y-%m-%d")
                if to_date > today:
                    ss = "ok"
                    from datetime import datetime as dt
                    res = (dt.strptime(to_date, "%Y-%m-%d") - dt.strptime(today, "%Y-%m-%d")).days
                    if res < 3:
                        ss = "not"
                        if i.status == "Completed":
                            ss = "ok"
                    else:
                        ss = "ok"
                else:
                    if i.status == "Completed":
                        ss = "ok"
                    else:
                        ss = "no"
                l.append({'ss': ss, 'WORK': i.WORK, 'date': i.date, 'status': i.status, 'progress': i.progress,'todate': to_date})
        return render(request, 'Project Manager/View Project Status.html', {'data': res2,'data1':l, 'id': id})
    else:
        id = request.POST['pid']
        p = project.objects.get(id=id)
        frm=request.POST['from']
        to=request.POST['to']
        res = work_progress.objects.filter(PROJECT=p,date__range=[frm,to])
        res2 = project_manager_allocation.objects.get(PROJECT=id, STAFF=request.session["sid"],
                                                      PROJECT__status='ongoing')
        wp = len(res)
        wpc = len(work_progress.objects.filter(status='Completed'))
        if (wp == wpc):
            pass
        else:
            pass
        l = []
        for i in res:
            ws = schedule.objects.filter(WORK=i.WORK, PROJECT=i.PROJECT)
            if ws.exists():
                a = ws[0].to_date
                import datetime
                to_date = datetime.datetime.strftime(a, '%Y-%m-%d')
                today = datetime.datetime.now().strftime("%Y-%m-%d")
                if to_date > today:
                    ss = "ok"
                    from datetime import datetime as dt
                    res = (dt.strptime(to_date, "%Y-%m-%d") - dt.strptime(today, "%Y-%m-%d")).days
                    if res < 3:
                        ss = "not"
                        if i.status == "Completed":
                            ss = "ok"
                    else:
                        ss = "ok"
                else:
                    if i.status == "Completed":
                        ss = "ok"
                    else:
                        ss = "no"
                l.append({'ss': ss, 'WORK': i.WORK, 'date': i.date, 'status': i.status, 'progress': i.progress,'todate': to_date})
        return render(request, 'Project Manager/View Project Status.html', {'data': res2,'data1':l, 'id': id})

def View_Subcontractor_of_project(request,id):
    res=subcotractor_project_allocation.objects.filter(PROJECT=id)
    res2 = project_manager_allocation.objects.get(PROJECT=id, STAFF=request.session["sid"], PROJECT__status='ongoing')
    return render(request, 'Project Manager/View Subcontractor of Project.html',{'data':res2,'data2':res,'id':id})

def search_sbcrpm(request):
    id = request.POST['pid']
    p = project.objects.get(pk=id)
    w=request.POST['text']
    res = subcotractor_project_allocation.objects.filter(PROJECT=p,SUBCONTRACTOR__name__icontains=w)
    res2 = project_manager_allocation.objects.get(PROJECT=id, STAFF=request.session["sid"], PROJECT__status='ongoing')
    return render(request, 'Project Manager/View Subcontractor of Project.html', {'data': res2,'data2':res,'id':id})

def View_subcontractor_schedule(request,id):
    res=subcontractor_schedule.objects.filter(SUBCONTRACTOR_PROJECT_ALLOCATION=id)
    return render(request, 'Project Manager/View Subcontractor Schedule.html',{'data':res})

def View_subcontractor(request):
    res=subcontractor.objects.all()
    return render(request, 'Project Manager/View Subcontractor.html',{'data':res})

def search_sbr(request):
    w=request.POST['text']
    res = subcontractor.objects.filter(name__icontains=w)
    return render(request, 'Project Manager/View Subcontractor.html', {'data': res})

def View_uploaded_document(request,id):
    res=documents.objects.filter(PROJECT=id)
    res2 = project_manager_allocation.objects.get(PROJECT=id, STAFF=request.session["sid"], PROJECT__status='ongoing')
    return render(request, 'Project Manager/View Uploaded document.html',{
        'data': res2, 'data1': res, 'id': id,
        'workflow_document_rows': project_document.objects.filter(transferred_to_id=id),
        'quotation_rows': quotation.objects.filter(
            ENQUIRY__PROJECT_id=id, status='accepted',
        ).select_related('ENQUIRY'),
    })

def search_udcms(request):
    id = request.POST['pid']
    p = project.objects.get(pk=id)
    frm = request.POST['from']
    to = request.POST['to']
    res = documents.objects.filter(PROJECT=p,date__range=[frm,to])
    res2 = project_manager_allocation.objects.get(PROJECT=id, STAFF=request.session["sid"], PROJECT__status='ongoing')
    return render(request, 'Project Manager/View Uploaded document.html', {
        'data': res2, 'data1': res, 'id': id,
        'workflow_document_rows': project_document.objects.filter(transferred_to_id=id),
        'quotation_rows': quotation.objects.filter(
            ENQUIRY__PROJECT_id=id, status='accepted',
        ).select_related('ENQUIRY'),
    })

def View_uploaded_drawings(request,id):
    res=drawing.objects.filter(PROJECT=id)
    res2 = project_manager_allocation.objects.get(PROJECT=id, STAFF=request.session["sid"], PROJECT__status='ongoing')
    return render(request, 'Project Manager/View Uploaded Drawings.html',{'data':res2,'data1':res,'id':id})

def search_udrws(request):
    id = request.POST['pid']
    p = project.objects.get(pk=id)
    frm = request.POST['from']
    to = request.POST['to']
    res = drawing.objects.filter(PROJECT=p,date__range=[frm,to])
    res2 = project_manager_allocation.objects.get(PROJECT=id, STAFF=request.session["sid"], PROJECT__status='ongoing')
    return render(request, 'Project Manager/View Uploaded Drawings.html', {'data': res2,'data1':res, 'id': id})

def View_work_schedules(request,id):
    res=schedule.objects.filter(PROJECT=id)
    res2 = project_manager_allocation.objects.get(PROJECT=id, STAFF=request.session["sid"], PROJECT__status='ongoing')
    return render(request, 'Project Manager/View Work Schedules.html',{'data':res2,'data1':res,'id':id})

def schedule_searchpm(request):
    id = request.POST['pid']
    P = project.objects.get(id=id)
    frm=request.POST['from']
    to=request.POST['to']
    res=schedule.objects.filter(from_date__range=[frm,to],to_date__range=[frm,to],PROJECT=P)
    res2 = project.objects.get(id=id, status='ongoing')
    return render(request, 'Project Manager/View Work Schedules.html', {'data': res2,'data1':res,'id':id})

def View_work(request,id):
    res=work.objects.filter(PROJECT=id)
    res2 = project_manager_allocation.objects.get(PROJECT=id, STAFF=request.session["sid"], PROJECT__status='ongoing')
    return render(request, 'Project Manager/View Work.html',{'data':res2,'data1':res,'id':id})

def search_wrk(request):
    id = request.POST['pid']
    p = project.objects.get(id=id)
    w=request.POST['textfield']
    res = work.objects.filter(workname__icontains=w,PROJECT=p)
    res2 = project_manager_allocation.objects.get(PROJECT=id, STAFF=request.session["sid"], PROJECT__status='ongoing')
    return render(request, 'Project Manager/View Work.html', {'data': res2,'data1':res, 'id': id})

def View_Worksite_photospm(request,id):
    res=photo.objects.filter(PROJECT=id)
    res2 = project_manager_allocation.objects.get(PROJECT=id, STAFF=request.session["sid"], PROJECT__status='ongoing')
    return render(request,'Project Manager/View Worksite Photos.html',{'data':res2,'data2':res,'id':id})

def search_sppm(request):
    id = request.POST['pid']
    p = project.objects.get(id=id)
    frm=request.POST['from']
    to=request.POST['to']
    res = photo.objects.filter(date__range=[frm,to],PROJECT=p)
    res2 = project_manager_allocation.objects.get(PROJECT=id, STAFF=request.session["sid"], PROJECT__status='ongoing')
    return render(request, 'Project Manager/View Worksite Photos.html', {'data': res2,'data2':res, 'id': id})

#########################################  SUPERVISOR  ###################################################################

def sphome(request):
    return render(request,'Supervisor/spindex.html')

def Add_daily_material_usage(request,id):
    res=project.objects.get(id=id)
    m=material.objects.all()
    return render(request, 'Supervisor/Add Daily Material Usage.html',{'data':res,'data1':m,'id':id})

def Add_daily_material_usage_post(request):
    id=request.POST['id']
    pid=request.POST['pid']
    p=project.objects.get(id=pid)
    mtl=request.POST['material']
    m=material.objects.get(id=mtl)
    quantity=request.POST['quantity']
    # unit=request.POST['unit']
    sid=request.session['lid']
    s=staff.objects.get(LOGIN=sid)
    from datetime import datetime

    admj=material_usage()
    admj.PROJECT=p
    admj.quantity=quantity
    # admj.unit=unit
    admj.MATERIAL=m
    admj.STAFF=s
    admj.date=datetime.now().strftime("%Y-%m-%d")
    admj.save()
    return HttpResponse("<script>alert('Added Successfully');window.location='/WMS/View_daily_materials_usage/"+id+"#myid'</script>")

def Add_daily_workers_count(request,id):
    res=project.objects.get(id=id)
    return render(request, 'Supervisor/Add Daily Workers Count.html',{'data':res,'id':id})

def Add_daily_workers_count_post(request):
    id=request.POST['id']
    pid=request.POST['pid']
    p=project.objects.get(id=pid)
    worktype=request.POST['worktype']
    workercount=request.POST['workercount']
    from datetime import datetime

    adwj=worker_entry()
    adwj.date=datetime.now().strftime("%Y-%m-%d")
    adwj.PROJECT=p
    adwj.work_type=worktype
    adwj.worker_count=workercount
    adwj.save()
    return HttpResponse("<script>alert('Added Successfully');window.location='/WMS/View_daily_workers_count/"+id+"#myid'</script>")

def Change_password_sp(request):
    return render(request,'Supervisor/Change Password.html')

def Change_password_sp_post(request):
    return _change_session_password(request, '/WMS/Change_password_sp/')

def Edit_daily_material_usage(request,id,pid):
    res=material_usage.objects.get(id=id)
    m=material.objects.all()
    return render(request, 'Supervisor/Edit Daily Material Usage.html',{'data':res,'data1':m,'pid':pid})

def Edit_daily_material_usage_post(request):
    pid=request.POST['pid']
    eid=request.POST['eid']
    mtl=request.POST['material']
    m=material.objects.get(id=mtl)
    quantity=request.POST['quantity']
    # unit=request.POST['unit']

    material_usage.objects.filter(id=eid).update(quantity = quantity,MATERIAL = m)
    return HttpResponse("<script>alert('Edited Succefully');window.location='/WMS/View_daily_materials_usage/"+pid+"#myid'</script>")

def Delete_muse(request,id,pid):
    material_usage.objects.get(id=id).delete()
    return HttpResponse("<script>alert('Deleted Successfully');window.location='/WMS/View_daily_materials_usage/"+pid+"#myid'</script>")

def Edit_daily_workers_count(request,id,pid):
    res=worker_entry.objects.get(id=id)
    return render(request, 'Supervisor/Edit Daily Workers Count.html',{'data':res,'pid':pid})

def Edit_daily_workers_count_post(request):
    pid=request.POST['pid']
    eid=request.POST['eid']
    worktype=request.POST['worktype']
    workercount=request.POST['workercount']
    worker_entry.objects.filter(id=eid).update(work_type = worktype,worker_count = workercount)
    return HttpResponse("<script>alert('Edited Successfully');window.location='/WMS/View_daily_workers_count/"+pid+"#myid'</script>")

def Delete_dwc(request,id,pid):
    worker_entry.objects.filter(id=id).delete()
    return HttpResponse("<script>alert('Deleted Successfully');window.location='/WMS/View_daily_workers_count/"+pid+"#myid'</script>")

def Edit_material_request(request,id,pid):
    res=material_request.objects.get(id=id)
    m=material_required.objects.filter(PROJECT=pid).select_related('MATERIAL')
    return render(request, 'Supervisor/Edit Material Request.html',{'data':res,'data1':m,'pid':pid})

def Edit_material_request_post(request):
    pid=request.POST['pid']
    mid=request.POST['mid']
    mtl=request.POST['material']
    m=material.objects.get(id=mtl)
    quantity=request.POST['quantity']
    material_request.objects.filter(id=mid, PROJECT_id=pid).update(MATERIAL=m,quantity=quantity)
    return HttpResponse("<script>alert('Edited Successfully');window.location='/WMS/View_material_request/"+pid+"#myid'</script>")

def Delete_mrt(request,id,pid):
    material_request.objects.filter(id=id).delete()
    return HttpResponse("<script>alert('Deleted Successfully');window.location='/WMS/View_material_request/"+pid+"#myid'</script>")

def Edit_Uploaded_site_photos(request,id,pid):
    res=photo.objects.get(id=id)
    return render(request, 'Supervisor/Edit Uploaded Site Photos.html',{'data':res,'pid':pid})

def Edit_Uploaded_site_photos_post(request):
    pid=request.POST['pid']
    eid=request.POST['eid']
    e=photo.objects.get(id=eid).id
    pt=request.FILES['photo']
    from datetime import datetime
    fs=FileSystemStorage()
    date=datetime.now().strftime("%Y%m%d%H%M%S")+pt.name
    ft=fs.save(date,pt)

    photo.objects.filter(id=e).update(photo=fs.url(ft))
    return HttpResponse("<script>alert('Edited Successfully');window.location='/WMS/View_Uploaded_site_photos/"+pid+"#myid'</script>")

def Delete_usp(request,id,pid):
    photo.objects.filter(id=id).delete()
    return HttpResponse("<script>alert('Deleted Successfully');window.location='/WMS/View_Uploaded_site_photos/"+pid+"#myid'</script>")

def Delete_chatsp(request,id,pid):
    lid=request.session['lid']
    chat.objects.filter(id=id, LOGIN_id=lid).delete()
    p=project.objects.get(id=pid).project_name
    return render(request,'Supervisor/fur_chat.html', {'id':pid,'lid':lid,'p':p})

def chatssp(request,id,msg):
    lid=str(request.session['lid'])
    from datetime import datetime

    sender = staff.objects.get(LOGIN_id=lid)

    d=chat()
    d.LOGIN_id=lid
    d.PROJECT_id=id
    d.message=msg
    d.date=datetime.now().strftime("%Y-%m-%d")
    d.time=datetime.now().strftime("%I:%M %p")
    d.type=sender.name+" , "+sender.designation
    d.save()
    return JsonResponse({'status':'ok'})

def chatsp(request,id):
    lid=request.session['lid']
    p=project.objects.get(id=id).project_name
    return render(request,'Supervisor/fur_chat.html', {'id':id,'lid':lid,'p':p})

def viewmsg_sp(request,id):
    return JsonResponse({'data': _chat_messages(id, request.session['lid'])})

def Send_material_request(request,id):
    res=supervisor_allocation.objects.get(PROJECT=id,STAFF=request.session["sid"])
    m=material_required.objects.filter(PROJECT=id)
    return render(request, 'Supervisor/Send Material Request.html',{'data':res,'data1':m,'id':id})

def Send_material_request_post(request):
    pid=request.POST['pid']
    id=request.POST['id']
    p=project.objects.get(id=pid)
    mtl=request.POST['material']
    m=material.objects.get(id=mtl)
    quantity=request.POST['quantity']
    # unit=request.POST['unit']
    s=staff.objects.get(id=request.session["sid"])
    from datetime import datetime
    mtlrd=material_request.objects.filter(PROJECT=p,MATERIAL=m)
    mtlrt=material_required.objects.get(PROJECT=p,MATERIAL=m)
    ttlq=0
    for i in mtlrd:
        ttlq += int(i.quantity)
    tt=ttlq+int(quantity)
    if tt > int(mtlrt.quantity):
        nt=notification()
        nt.notification=s.name+"Requested Material More Than Required"
        nt.status='pending'
        nt.date=datetime.now().strftime("%Y-%m-%d")
        nt.type='material request'
        nt.STAFF=s
        nt.PROJECT=p
        nt.save()
        smrj=material_request()
        smrj.PROJECT=p
        smrj.STAFF=s
        smrj.MATERIAL=m
        smrj.date=datetime.now().strftime("%Y-%m-%d")
        smrj.quantity=quantity
        # smrj.unit=unit
        smrj.status="pending"
        smrj.save()
        return HttpResponse("<script>alert('Send Successfully');window.location='/WMS/View_material_request/"+id+"#myid'</script>")
    else:
        smrj = material_request()
        smrj.PROJECT = p
        smrj.STAFF = s
        smrj.MATERIAL = m
        smrj.date = datetime.now().strftime("%Y-%m-%d")
        smrj.quantity = quantity
        # smrj.unit = unit
        smrj.status = "pending"
        smrj.save()
        return HttpResponse("<script>alert('Send Successfully');window.location='/WMS/View_material_request/"+id+"#myid'</script>")

def Update_work_progress(request,id,pid):
    res=work.objects.get(id=id,PROJECT=pid)
    from datetime import datetime
    wpobj, _ = work_progress.objects.get_or_create(
        WORK=res,
        PROJECT_id=pid,
        defaults={
            'date': datetime.now().strftime("%Y-%m-%d"),
            'status': 'pending',
            'progress': '0',
        },
    )
    return render(request, 'Supervisor/Update Work Progress.html',{'data':res,'data2':wpobj})

def Update_work_progress_post(request):
    pid=request.POST['pid']
    p=project.objects.get(id=pid)
    wid=request.POST['wid']
    w=work.objects.get(id=wid)
    status=request.POST['status']
    progress=request.POST['progress']
    from datetime import datetime
    d = datetime.now().strftime("%Y-%m-%d")

    work_progress.objects.filter(WORK=w,PROJECT=p).update(status=status,progress=progress,date=d)
    return HttpResponse("<script>alert('Updated Successfully');window.location='/WMS/Update_work_progress/"+wid+"/"+pid+"'</script>")

def Upload_site_photos(request,id):
    res=supervisor_allocation.objects.get(PROJECT=id,STAFF=request.session["sid"])
    return render(request, 'Supervisor/Upload Site Photos.html',{'data':res})

def Upload_site_photos_post(request):
    pid=request.POST['pid']
    p=project.objects.get(id=pid)
    aid=request.POST['aid']
    a=supervisor_allocation.objects.get(id=aid)
    pt=request.FILES['photo']
    from datetime import datetime
    fs=FileSystemStorage()
    d=datetime.now().strftime("%Y%m%d%H%M%S")+pt.name
    fn=fs.save(d,pt)

    euj = photo()
    euj.photo = fs.url(fn)
    euj.PROJECT=p
    euj.date=datetime.now().strftime("%Y-%m-%d")
    euj.ALLOCATION=a
    euj.save()
    return HttpResponse("<script>alert('Uploaded');window.location='/WMS/View_Uploaded_site_photos/"+pid+"#myid'</script>")

def View_assigned_projects_sp(request):
    res=supervisor_allocation.objects.filter(STAFF=request.session["sid"])
    return render(request, 'Supervisor/View Assigned Projects.html',{'data':res,'id':id})

def search_asp(request):
    button=request.POST['button']
    if button == 'Search':
        txt=request.POST['text']
        res = supervisor_allocation.objects.filter(STAFF=request.session["sid"],PROJECT__project_name__icontains=txt)
        return render(request, 'Supervisor/View Assigned Projects.html', {'data': res, 'id': id})
    else:
        frm=request.POST['from']
        to=request.POST['to']
        res = supervisor_allocation.objects.filter(STAFF=request.session["sid"],PROJECT__date__range=[frm,to])
        return render(request, 'Supervisor/View Assigned Projects.html', {'data': res, 'id': id})

def View_budget_sp(request,id):
    res=budget_estimate.objects.filter(ESTIMATE=id)
    return render(request, 'Supervisor/View Budget.html', {'data':res, 'id':id})

def search_bgtsp(request):
    id = request.POST['id']
    c=request.POST['textfield']
    res = budget_estimate.objects.filter(work_category__icontains=c,ESTIMATE=id)
    return render(request, 'Supervisor/View Budget.html', {'data':res, 'id':id})

def View_completed_projects_sp(request):
    res=supervisor_allocation.objects.filter(STAFF=request.session["sid"],PROJECT__status='Completed')
    return render(request, 'Supervisor/View Completed Projects.html',{'data':res,'id':id})

def search_aspcp(request):
    button=request.POST['button']
    if button == 'Search':
        txt=request.POST['text']
        res = supervisor_allocation.objects.filter(STAFF=request.session["sid"],PROJECT__status='completed',PROJECT__project_name__icontains=txt)
        return render(request, 'Supervisor/View Completed Projects.html', {'data': res, 'id': id})
    else:
        frm=request.POST['from']
        to=request.POST['to']
        res = supervisor_allocation.objects.filter(STAFF=request.session["sid"],PROJECT__status='completed',PROJECT__date__range=[frm,to])
        return render(request, 'Supervisor/View Completed Projects.html', {'data': res, 'id': id})

def View_daily_workers_count(request,id):
    res=worker_entry.objects.filter(PROJECT=id)
    res2 = supervisor_allocation.objects.get(PROJECT=id, STAFF=request.session["sid"], PROJECT__status='ongoing')
    return render(request, 'Supervisor/View Daily Workers Count.html',{'data':res2,'data1':res,'id':id})

def search_dwcr(request):
    button=request.POST['button']
    if button == "Search":
        id = request.POST['pid']
        p = project.objects.get(id=id)
        frm=request.POST['from']
        to=request.POST['to']
        res = worker_entry.objects.filter(date__range=[frm,to],PROJECT=p)
        res2 = supervisor_allocation.objects.get(PROJECT=id, STAFF=request.session["sid"], PROJECT__status='ongoing')
        return render(request, 'Supervisor/View Daily Workers Count.html', {'data': res2,'data1':res, 'id': id})
    else:
        id = request.POST['pid']
        p = project.objects.get(id=id)
        text=request.POST['txt']
        res = worker_entry.objects.filter(work_type__icontains=text, PROJECT=p)
        res2 = supervisor_allocation.objects.get(PROJECT=id, STAFF=request.session["sid"], PROJECT__status='ongoing')
        return render(request, 'Supervisor/View Daily Workers Count.html', {'data': res2,'data1':res, 'id': id})

def View_daily_materials_usage(request,id):
    res=material_usage.objects.filter(STAFF=request.session["sid"],PROJECT=id)
    res2 = supervisor_allocation.objects.get(PROJECT=id, STAFF=request.session["sid"], PROJECT__status='ongoing')
    return render(request, 'Supervisor/View Daily Material Usage.html',{'data':res2,'data1':res,'id':id})

def search_dmur(request):
    button = request.POST['button']
    if button == 'Search':
        id = request.POST['pid']
        project.objects.get(pk=id)
        txt = request.POST['text']
        res = material_usage.objects.filter(STAFF=request.session["sid"], PROJECT=id,  MATERIAL__name__icontains=txt)
        res2 = supervisor_allocation.objects.get(PROJECT=id, STAFF=request.session["sid"], PROJECT__status='ongoing')
        return render(request, 'Supervisor/View Daily Material Usage.html', {'data': res2,'data1':res, 'id': id})
    else:
        id = request.POST['pid']
        project.objects.get(pk=id)
        frm = request.POST['from']
        to = request.POST['to']
        res = material_usage.objects.filter(STAFF=request.session["sid"], PROJECT=id, date__range=[frm, to])
        res2 = supervisor_allocation.objects.get(PROJECT=id, STAFF=request.session["sid"], PROJECT__status='ongoing')
        return render(request, 'Supervisor/View Daily Material Usage.html', {'data': res2,'data1':res, 'id': id})

def View_drawings(request,id):
    res=drawing.objects.filter(PROJECT=id)
    res2 = supervisor_allocation.objects.get(PROJECT=id, STAFF=request.session["sid"], PROJECT__status='ongoing')
    return render(request, 'Supervisor/View Drawings.html',{'data':res2,'data1':res,'id':id})

def search_drws(request):
    id = request.POST['pid']
    p = project.objects.get(pk=id)
    frm = request.POST['from']
    to = request.POST['to']
    res = drawing.objects.filter(PROJECT=p,date__range=[frm,to])
    res2 = supervisor_allocation.objects.get(PROJECT=id, STAFF=request.session["sid"], PROJECT__status='ongoing')
    return render(request, 'Supervisor/View Drawings.html', {'data': res2,'data1':res, 'id': id})

def View_documents(request,id):
    res=documents.objects.filter(PROJECT=id)
    res2 = supervisor_allocation.objects.get(PROJECT=id, STAFF=request.session["sid"], PROJECT__status='ongoing')
    return render(request, 'Supervisor/View document.html',{'data':res2,'data1':res,'id':id})

def search_dcms(request):
    id = request.POST['pid']
    p = project.objects.get(pk=id)
    frm = request.POST['from']
    to = request.POST['to']
    res = documents.objects.filter(PROJECT=p,date__range=[frm,to])
    res2 = supervisor_allocation.objects.get(PROJECT=id, STAFF=request.session["sid"], PROJECT__status='ongoing')
    return render(request, 'Supervisor/View document.html', {'data': res2,'data1':res,'id':id})

def View_estimate_sp(request,id):
    res=estimate.objects.filter(PROJECT=id)
    tt=[]
    for i in res:
        j=budget_estimate.objects.filter(ESTIMATE_id=i.id)
        myval=0
        for k in j:
            myval+=float(k.total)
        tt.append({"id":i.id,"date":i.date,"est_no":i.est_no,"PROJECT":i.PROJECT.id,"my":myval})
    res2 = supervisor_allocation.objects.get(PROJECT=id, STAFF=request.session["sid"], PROJECT__status='ongoing')
    return render(request, 'Supervisor/View Estimate.html',{'data':res2,'data1':tt,'id':id})

def search_estm(request):
    id = request.POST['pid']
    p = project.objects.get(pk=id)
    frm = request.POST['from']
    to = request.POST['to']
    res = estimate.objects.filter(PROJECT=p,date__range=[frm,to])
    tt = []
    for i in res:
        j = budget_estimate.objects.filter(ESTIMATE_id=i.id)
        myval = 0
        for k in j:
            myval += float(k.total)
        tt.append({"id": i.id, "date": i.date, "est_no": i.est_no, "PROJECT": i.PROJECT.id, "my": myval})
    res2 = supervisor_allocation.objects.get(PROJECT=id, STAFF=request.session["sid"], PROJECT__status='ongoing')
    return render(request, 'Supervisor/View Estimate.html', {'data': res2,'data1':tt,'id':id})

def View_inspection_details(request,id):
    res=inspection.objects.filter(PROJECT=id)
    res2 = supervisor_allocation.objects.get(PROJECT=id, STAFF=request.session["sid"], PROJECT__status='ongoing')
    return render(request, 'Supervisor/View Inspection Details.html',{'data':res2,'data1':res,'id':id})

def search_inspection(request):
    id = request.POST['pid']
    p = project.objects.get(pk=id)
    frm=request.POST['from']
    to=request.POST['to']
    res = inspection.objects.filter(PROJECT=p,date__range=[frm,to])
    res2 = supervisor_allocation.objects.get(PROJECT=id, STAFF=request.session["sid"], PROJECT__status='ongoing')
    return render(request, 'Supervisor/View Inspection Details.html', {'data': res2,'data1':res,'id':id})

def View_material_request_report(request,id):
    res=material_request.objects.filter(PROJECT=id,STAFF=request.session["sid"])
    res2 = supervisor_allocation.objects.get(PROJECT=id, STAFF=request.session["sid"], PROJECT__status='ongoing')
    return render(request, 'Supervisor/View Material Request Report.html',{'data':res2,'data1':res,'id':id})

def search_mrr(request):
    button = request.POST['button']
    if button == 'Search':
        id = request.POST['pid']
        p = project.objects.get(pk=id)
        txt = request.POST['text']
        res = material_request.objects.filter(PROJECT=p,STAFF=request.session["sid"], MATERIAL__name__icontains=txt)
        res2 = supervisor_allocation.objects.get(PROJECT=id, STAFF=request.session["sid"], PROJECT__status='ongoing')
        return render(request, 'Supervisor/View Material Request Report.html', {'data': res2,'data1':res, 'id': id})
    else:
        id = request.POST['pid']
        p = project.objects.get(pk=id)
        frm = request.POST['from']
        to = request.POST['to']
        res = material_request.objects.filter(PROJECT=p,STAFF=request.session["sid"], date__range=[frm, to])
        res2 = supervisor_allocation.objects.get(PROJECT=id, STAFF=request.session["sid"], PROJECT__status='ongoing')
        return render(request, 'Supervisor/View Material Request Report.html', {'data': res2,'data1':res, 'id': id})

def View_material_request(request,id):
    res=material_request.objects.filter(PROJECT=id,STAFF=request.session["sid"],status='approved')
    res2 = supervisor_allocation.objects.get(PROJECT=id, STAFF=request.session["sid"], PROJECT__status='ongoing')
    return render(request, 'Supervisor/View Material Request.html',{'data':res2,'data1':res,'id':id})

def search_mr(request):
    button = request.POST['button']
    if button == 'Search':
        id = request.POST['pid']
        p = project.objects.get(pk=id)
        txt = request.POST['text']
        res = material_request.objects.filter(status='approved',PROJECT=p,STAFF=request.session["sid"], MATERIAL__name__icontains=txt)
        res2 = supervisor_allocation.objects.get(PROJECT=id, STAFF=request.session["sid"], PROJECT__status='ongoing')
        return render(request, 'Supervisor/View Material Request.html', {'data': res2,'data1':res, 'id': id})
    else:
        id = request.POST['pid']
        p = project.objects.get(pk=id)
        frm = request.POST['from']
        to = request.POST['to']
        res = material_request.objects.filter(status='approved',PROJECT=p,STAFF=request.session["sid"], date__range=[frm, to])
        res2 = supervisor_allocation.objects.get(PROJECT=id, STAFF=request.session["sid"], PROJECT__status='ongoing')
        return render(request, 'Supervisor/View Material Request.html', {'data': res2,'data1':res, 'id': id})

def View_material_usage_report(request,id):
    res=material_usage.objects.filter(PROJECT=id,STAFF=request.session["sid"])
    res2 = supervisor_allocation.objects.get(PROJECT=id, STAFF=request.session["sid"], PROJECT__status='ongoing')
    return render(request, 'Supervisor/View Material Usage Report.html',{'data':res2,'data1':res,'id':id})

def search_mur(request):
    button = request.POST['button']
    if button == 'Search':
        id = request.POST['pid']
        p = project.objects.get(pk=id)
        txt = request.POST['text']
        res = material_usage.objects.filter(PROJECT=p, STAFF=request.session["sid"],MATERIAL__name__icontains=txt)
        res2 = supervisor_allocation.objects.get(PROJECT=id, STAFF=request.session["sid"], PROJECT__status='ongoing')
        return render(request, 'Supervisor/View Material Usage Report.html', {'data': res2,'data1':res, 'id': id})
    else:
        id = request.POST['pid']
        p = project.objects.get(pk=id)
        frm = request.POST['from']
        to = request.POST['to']
        res = material_usage.objects.filter(PROJECT=p, STAFF=request.session["sid"], date__range=[frm, to])
        res2 = supervisor_allocation.objects.get(PROJECT=id, STAFF=request.session["sid"], PROJECT__status='ongoing')
        return render(request, 'Supervisor/View Material Usage Report.html', {'data': res2,'data1':res, 'id': id})

def View_material_issued_and_update_status(request,id):
    res=material_issued.objects.filter(PROJECT=id,STAFF=request.session["sid"])
    res2 = supervisor_allocation.objects.get(PROJECT=id, STAFF=request.session["sid"], PROJECT__status='ongoing')
    return render(request, 'Supervisor/View Materials Issued & Update Status.html',{'data':res2,'data1':res,'id':id})

def Update_issue_status(request,id):
    material_issued.objects.filter(pk=id).update(status='recieved')
    return HttpResponse("<script>alert('Updated');window.location='/WMS/View_material_issued_and_update_status/"+id+"#myid'</script>")

def search_misd(request):
    button = request.POST['button']
    if button == 'Search':
        id = request.POST['pid']
        p = project.objects.get(pk=id)
        txt = request.POST['text']
        res = material_issued.objects.filter(PROJECT=p,STAFF=request.session["sid"], MATERIAL__name__icontains=txt)
        res2 = supervisor_allocation.objects.get(PROJECT=id, STAFF=request.session["sid"], PROJECT__status='ongoing')
        return render(request, 'Supervisor/View Materials Issued & Update Status.html', {'data': res2,'data1':res, 'id': id})
    else:
        id = request.POST['pid']
        p = project.objects.get(pk=id)
        frm = request.POST['from']
        to = request.POST['to']
        res = material_issued.objects.filter(PROJECT=p,STAFF=request.session["sid"],date__range=[frm, to])
        res2 = supervisor_allocation.objects.get(PROJECT=id, STAFF=request.session["sid"], PROJECT__status='ongoing')
        return render(request, 'Supervisor/View Materials Issued & Update Status.html', {'data': res2,'data1':res, 'id': id})

def View_material_required(request,id):
    res=material_required.objects.filter(PROJECT=id)
    res2 = supervisor_allocation.objects.get(PROJECT=id, STAFF=request.session["sid"], PROJECT__status='ongoing')
    return render(request, 'Supervisor/View Materials Required.html',{'data':res2,'data1':res,'id':id})

def search_mrd(request):
    id = request.POST['id']
    p=project.objects.get(pk=id)
    txt = request.POST['text']
    res = material_required.objects.filter(MATERIAL__name__icontains=txt,PROJECT=p)
    res2 = supervisor_allocation.objects.get(PROJECT=id, STAFF=request.session["sid"], PROJECT__status='ongoing')
    return render(request, 'Supervisor/View Materials Required.html', {'data': res2,'data1':res,'id':id})

def View_Ongoing_project_sp(request):
    res=supervisor_allocation.objects.filter(STAFF=request.session["sid"],PROJECT__status='ongoing')
    return render(request, 'Supervisor/View Ongoing Project.html',{'data':res})

def search_ongp(request):
    button=request.POST['button']
    if button == 'Search':
        txt=request.POST['text']
        res = supervisor_allocation.objects.filter(status='ongoing',STAFF=request.session["sid"],PROJECT__project_name__icontains=txt)
        return render(request, 'Supervisor/View Ongoing Project.html', {'data': res})
    else:
        frm=request.POST['from']
        to=request.POST['to']
        res = supervisor_allocation.objects.filter(status='ongoing',STAFF=request.session["sid"],PROJECT__date__range=[frm,to])
        return render(request, 'Supervisor/View Ongoing Project.html', {'data': res})

def View_projects_functionsp(request,id):
    res = supervisor_allocation.objects.get(PROJECT=id,STAFF=request.session["sid"], PROJECT__status='ongoing')
    return render(request,'Supervisor/View Ongoing Projects Functions.html',{'data':res})

def View_profile_sp(request):
    res=staff.objects.get(LOGIN=request.session["lid"])
    return render(request, 'Supervisor/View Profile.html',{'data':res})

def View_project_payment(request,id):
    res=payemnt_entry.objects.filter(PROJECT=id)
    res2 = supervisor_allocation.objects.get(PROJECT=id, STAFF=request.session["sid"], PROJECT__status='ongoing')
    return render(request, 'Supervisor/View Project Payment Entry.html',{'data':res2,'data1':res,'id':id})

def search_payment(request):
    id=request.POST['pid']
    PROJECT = project.objects.get(id=id)
    frm=request.POST['from']
    to=request.POST['to']
    res = payemnt_entry.objects.filter(date__range=[frm,to],PROJECT=PROJECT)
    res2 = supervisor_allocation.objects.get(PROJECT=id, STAFF=request.session["sid"], PROJECT__status='ongoing')
    return render(request, 'Supervisor/View Project Payment Entry.html', {'data': res2,'data1':res,'id':id})

def View_schedule(request,id):
    res=schedule.objects.filter(PROJECT=id)
    res2 = supervisor_allocation.objects.get(PROJECT=id, STAFF=request.session["sid"], PROJECT__status='ongoing')
    return render(request, 'Supervisor/View Schedule.html',{'data':res2,'data1':res,'id':id})

def schedule_search(request):
    id = request.POST['pid']
    P = project.objects.get(id=id)
    frm=request.POST['from']
    to=request.POST['to']
    res=schedule.objects.filter(from_date__range=[frm,to],to_date__range=[frm,to],PROJECT=P)
    res2 = supervisor_allocation.objects.get(PROJECT=id, STAFF=request.session["sid"], PROJECT__status='ongoing')
    return render(request, 'Supervisor/View Schedule.html', {'data': res2,'data1':res,'id':id})

def View_subcontractor_schedule_sp(request,id):
    res=subcontractor_schedule.objects.filter(SUBCONTRACTOR_PROJECT_ALLOCATION=id)
    return render(request, 'Supervisor/View Subcontractor Schedule.html',{'data':res,'id':id})

def search_subsh(request):
    id = request.POST['pid']
    # p = project.objects.get(id=id)
    frm=request.POST['from']
    to=request.POST['to']
    res = subcontractor_schedule.objects.filter(from_date__range=[frm,to],to_date__range=[frm,to],SUBCONTRACTOR_PROJECT_ALLOCATION=id)
    return render(request, 'Supervisor/View Subcontractor Schedule.html', {'data': res,'id':id})

def View_Subcontractor(request,id):
    res=subcotractor_project_allocation.objects.filter(PROJECT=id)
    res2 = supervisor_allocation.objects.get(PROJECT=id, STAFF=request.session["sid"], PROJECT__status='ongoing')
    return render(request, 'Supervisor/View Subcontractor.html',{'data':res2,'data1':res,'id':id})

def search_subc(request):
    button=request.POST['button']
    if button == 'Search':
        id = request.POST['pid']
        p = project.objects.get(id=id)
        txt = request.POST['txt']
        res = subcotractor_project_allocation.objects.filter(SUBCONTRACTOR__name__icontains=txt,PROJECT=p)
        res2 = supervisor_allocation.objects.get(PROJECT=id, STAFF=request.session["sid"], PROJECT__status='ongoing')
        return render(request, 'Supervisor/View Subcontractor.html', {'data': res2,'data1':res,'id':id})
    else:
        id = request.POST['pid']
        p = project.objects.get(id=id)
        ctg = request.POST['ctg']
        res = subcotractor_project_allocation.objects.filter(WORK__workname__icontains=ctg,PROJECT=p)
        res2 = supervisor_allocation.objects.get(PROJECT=id, STAFF=request.session["sid"], PROJECT__status='ongoing')
        return render(request, 'Supervisor/View Subcontractor.html', {'data': res2,'data1':res,'id':id})

def View_Uploaded_site_photos(request,id):
    res=photo.objects.filter(PROJECT=id)
    res2 = supervisor_allocation.objects.get(PROJECT=id, STAFF=request.session["sid"], PROJECT__status='ongoing')
    return render(request, 'Supervisor/View Uploaded Site Photos.html',{'data':res2,'data1':res,'id':id})

def search_usp(request):
    id = request.POST['pid']
    p = project.objects.get(id=id)
    frm=request.POST['from']
    to=request.POST['to']
    res = photo.objects.filter(date__range=[frm,to],PROJECT=p)
    res2 = supervisor_allocation.objects.get(PROJECT=id, STAFF=request.session["sid"], PROJECT__status='ongoing')
    return render(request, 'Supervisor/View Uploaded Site Photos.html', {'data': res2,'data1':res,'id':id})

def View_work_progress(request,id,pid):
    res=work_progress.objects.filter(WORK=id,PROJECT=pid)
    if res.exists():
        res = work_progress.objects.get(WORK=id, PROJECT=pid)
        return render(request, 'Supervisor/View Work Progress.html',{'data':res,'id':id,'pid':pid})
    else:
        return HttpResponse("no data")

def Delete_wps(request,id,wid,pid):
    work_progress.objects.get(id=id).delete()
    return HttpResponse("<script>alert('Deleted');window.location='/WMS/View_work_progress/"+wid+"/"+pid+"'</script>")

def View_work_status_report(request,id):
    res=work_progress.objects.filter(PROJECT=id)
    res2 = supervisor_allocation.objects.get(PROJECT=id, STAFF=request.session["sid"], PROJECT__status='ongoing')
    l = []
    for i in res:
        ws = schedule.objects.filter(WORK=i.WORK, PROJECT=i.PROJECT)
        if ws.exists():
            a = ws[0].to_date
            import datetime
            to_date = datetime.datetime.strftime(a, '%Y-%m-%d')
            today = datetime.datetime.now().strftime("%Y-%m-%d")
            if to_date > today:
                ss = "ok"
                from datetime import datetime as dt
                res = (dt.strptime(to_date, "%Y-%m-%d") - dt.strptime(today, "%Y-%m-%d")).days
                if res < 3:
                    ss = "not"
                else:
                    ss = "ok"
            else:
                if i.status == "Completed":
                    ss = "ok"
                else:
                    ss = "no"
            l.append({'ss': ss, 'WORK': i.WORK, 'date': i.date, 'status': i.status, 'progress': i.progress,'todate': to_date})
    return render(request, 'Supervisor/View Work Staus Report.html',{'data':res2,'data1':l,'id':id})

def search_wsr(request):
    id = request.POST['pid']
    p = project.objects.get(id=id)
    frm=request.POST['from']
    to=request.POST['to']
    res=work_progress.objects.filter(date__range=[frm,to],PROJECT=p)
    res2 = supervisor_allocation.objects.get(PROJECT=id, STAFF=request.session["sid"], PROJECT__status='ongoing')
    l = []
    for i in res:
        ws = schedule.objects.filter(WORK=i.WORK, PROJECT=i.PROJECT)
        if ws.exists():
            a = ws[0].to_date
            import datetime
            to_date = datetime.datetime.strftime(a, '%Y-%m-%d')
            today = datetime.datetime.now().strftime("%Y-%m-%d")
            if to_date > today:
                ss = "ok"
                from datetime import datetime as dt
                res = (dt.strptime(to_date, "%Y-%m-%d") - dt.strptime(today, "%Y-%m-%d")).days
                if res < 3:
                    ss = "not"
                else:
                    ss = "ok"
            else:
                if i.status == "Completed":
                    ss = "ok"
                else:
                    ss = "no"
            l.append({'ss': ss, 'WORK': i.WORK, 'date': i.date, 'status': i.status, 'progress': i.progress,'todate': to_date})
    return render(request, 'Supervisor/View Work Staus Report.html',{'data':res2,'data1':l,'id':id})

def View_work_sp(request,id):
    res=work.objects.filter(PROJECT=id)
    res2 = supervisor_allocation.objects.get(PROJECT=id, STAFF=request.session["sid"], PROJECT__status='ongoing')
    return render(request, 'Supervisor/View Work.html',{'data':res2,'data1':res,'id':id})

def search_work(request):
    id = request.POST['pid']
    p = project.objects.get(id=id)
    w=request.POST['textfield']
    res=work.objects.filter(workname__icontains=w,PROJECT=p)
    res2 = supervisor_allocation.objects.get(PROJECT=id, STAFF=request.session["sid"], PROJECT__status='ongoing')
    return render(request, 'Supervisor/View Work.html', {'data': res2,'data1':res,'id':id})

def View_worker_count_report(request,id):
    res=worker_entry.objects.filter(PROJECT=id)
    res2 = supervisor_allocation.objects.get(PROJECT=id, STAFF=request.session["sid"], PROJECT__status='ongoing')
    return render(request, 'Supervisor/View Worker Count Reports.html',{'data':res2,'data1':res,'id':id})

def search_wcr(request):
    button=request.POST['button']
    if button == "Search":
        id = request.POST['pid']
        p = project.objects.get(id=id)
        frm=request.POST['from']
        to=request.POST['to']
        res=worker_entry.objects.filter(date__range=[frm,to],PROJECT=p)
        res2 = supervisor_allocation.objects.get(PROJECT=id, STAFF=request.session["sid"], PROJECT__status='ongoing')
        return render(request, 'Supervisor/View Worker Count Reports.html', {'data': res2,'data1':res,'id':id})
    else:
        id = request.POST['pid']
        p = project.objects.get(id=id)
        text=request.POST['txt']
        res = worker_entry.objects.filter(work_type__icontains=text,PROJECT=p)
        res2 = supervisor_allocation.objects.get(PROJECT=id, STAFF=request.session["sid"], PROJECT__status='ongoing')
        return render(request, 'Supervisor/View Worker Count Reports.html', {'data': res2,'data1':res,'id':id})



################################################  ACCONTANT  ##########################################################

def achome(request):
    return render(request,'Accountant/acindex.html')

def Add_account_sub(request):
    res=accounthead.objects.all()
    return render(request, 'Accountant/Add AccountSub.html',{'data':res})

def Add_account_sub_post(request):
    name=request.POST['name']
    amount=request.POST['amount']
    hid=request.POST['headname']
    id=accounthead.objects.get(id=hid)
    from datetime import datetime
    aasj=account_sub()
    aasj.date=datetime.now().strftime("%Y-%m-%d")
    aasj.account_sub_name=name
    aasj.amount=amount
    aasj.ACCOUNTHEAD=id
    aasj.save()
    return HttpResponse("<script>alert('Added Successfully');window.location='/WMS/Add_account_sub/'</script>")

def Add_accounthead(request):
    return render(request, 'Accountant/Add AcountHead.html')

def Add_accounthead_post(request):
    name=request.POST['headname']

    aaj=accounthead()
    aaj.headname=name
    aaj.save()
    return HttpResponse("<script>alert('Added Successfully');window.location='/WMS/Add_accounthead/'</script>")

def Change_password_ac(request):
    return render(request,'Accountant/Change Password.html')

def Change_password_ac_post(request):
    return _change_session_password(request, '/WMS/Change_password_ac/')

def Edit_accounthead(request,id):
    res=accounthead.objects.get(id=id)
    return render(request, 'Accountant/Edit AccountHead.html',{'data':res})

def Edit_accounthead_post(request):
    headname=request.POST['headname']
    aid=request.POST['aid']
    accounthead.objects.filter(id=aid).update( headname= headname)
    return HttpResponse("<script>alert('Edited Successfully');window.location='/WMS/View_account_head/'</script>")

def Delete_Accounthead(request,id):
    accounthead.objects.filter(id=id).delete()
    return HttpResponse("<script>alert('Deleted Successfully');window.location='/WMS/View_account_head/'</script>")

def Edit_account_sub(request,id):
    res=account_sub.objects.get(id=id)
    res2=accounthead.objects.all()
    return render(request, 'Accountant/Edit AccountSub.html',{'data':res,'data2':res2})

def Edit_account_sub_post(request):
    asid=request.POST['asid']
    aid=request.POST['headname']
    name=request.POST['name']
    amount=request.POST['amount']
    # selection tag default problem-left for validation stage
    account_sub.objects.filter(pk=asid).update(account_sub_name=name,amount=amount,ACCOUNTHEAD=aid)
    return HttpResponse("<script>alert('Edited Successfully');window.location='/WMS/View_accountsub/'</script>")

def Delete_Accountsub(request,id):
    account_sub.objects.filter(pk=id).delete()
    return HttpResponse("<script>alert('Deleted Successfully');window.location='/WMS/View_accountsub/'</script>")

def Edit_Project_payment_entry(request, id, pid):
    res = payemnt_entry.objects.get(id=id)
    return render(request, 'Accountant/Edit Project Payment Entry.html', {'data': res, 'pid': pid})

def Edit_Project_payment_entry_post(request):
    pid = request.POST['pid']
    pyid = request.POST['pyid']
    amount = request.POST['amount']
    payemnt_entry.objects.filter(pk=pyid).update(amount=amount)
    return HttpResponse("<script>alert('Edited Successfully');window.location='/WMS/View_project_payment_entry_ac/" + pid + "#myid'</script>")

def Delete_Payment(request, id, pid):
    payemnt_entry.objects.filter(pk=id).delete()
    return HttpResponse("<script>alert('Deleted Successfully');window.location='/WMS/View_project_payment_entry_ac/" + pid + "#myid'</script>")

def Edit_Transaction_entry(request,id):
    res=transaction.objects.get(id=id)
    return render(request, 'Accountant/Edit Transaction Entry.html',{'data':res})

def Edit_Transaction_entry_post(request):
    tid=request.POST['tid']
    type=request.POST['type']
    amount=request.POST['amount']
    title=request.POST['title']
    narration=request.POST['narration']
    transaction.objects.filter(pk=tid).update(amount=amount,type=type,narration=narration,title=title)
    return HttpResponse("<script>alert('Edited Successfully');window.location='/WMS/View_transaction_entry/'</script>")

def Delete_Transaction(request,id):
    transaction.objects.filter(pk=id).delete()
    return HttpResponse("<script>alert('Deleted Successfully');window.location='/WMS/View_transaction_entry/'</script>")

def Delete_chatac(request,id,pid):
    lid=request.session['lid']
    chat.objects.filter(id=id, LOGIN_id=lid).delete()
    p=project.objects.get(id=pid).project_name
    return render(request,'Accountant/fur_chat.html', {'id':pid,'lid':lid,'p':p})

def chatsac(request,id,msg):
    lid=str(request.session['lid'])
    from datetime import datetime

    sender = staff.objects.get(LOGIN_id=lid)

    d=chat()
    d.LOGIN_id=lid
    d.PROJECT_id=id
    d.message=msg
    d.date=datetime.now().strftime("%Y-%m-%d")
    d.time=datetime.now().strftime("%I:%M %p")
    d.type=sender.name+" , "+sender.designation
    d.save()
    return JsonResponse({'status':'ok'})

def chatac(request,id):
    lid=request.session['lid']
    p=project.objects.get(id=id).project_name
    return render(request,'Accountant/fur_chat.html', {'id':id,'lid':lid,'p':p})

def viewmsg_ac(request,id):
    return JsonResponse({'data': _chat_messages(id, request.session['lid'])})

def Project_payment_entry(request,id):
    res=project.objects.get(pk=id)
    return render(request, 'Accountant/Project Payment Entry.html',{'data':res})

def Project_payment_entry_post(request):
    pid=request.POST['pid']
    res=project.objects.get(id=pid)
    amount=request.POST['amount']
    from datetime import datetime

    pj = payemnt_entry()
    pj.amount = amount
    pj.PROJECT=res
    pj.date=datetime.now().strftime("%Y-%m-%d")
    pj.save()
    return HttpResponse("<script>alert('Added Successfully');window.location='/WMS/View_project_payment_entry_ac/"+pid+"#myid'</script>")

def Transaction_entry(request):
    return render(request, 'Accountant/Transaction Entry.html')

def Transaction_entry_post(request):
    type=request.POST['type']
    amount=request.POST['amount']
    title=request.POST['title']
    narration=request.POST['narration']
    from datetime import datetime

    tj = transaction()
    tj.amount = amount
    tj.type = type
    tj.narration = narration
    tj.title = title
    tj.date=datetime.now().strftime("%Y-%m-%d")
    tj.save()
    return HttpResponse("<script>alert('Added Successfully');window.location='/WMS/Transaction_entry/'</script>")

def View_account_head(request):
    res=accounthead.objects.all()
    return render(request, 'Accountant/View Account Head.html',{'data':res})

def search_achd(request):
    w=request.POST['text']
    res = accounthead.objects.filter(headname__icontains=w)
    return render(request, 'Accountant/View Account Head.html', {'data': res})

def View_accountsub(request):
    res=account_sub.objects.all()
    return render(request, 'Accountant/View AccountSub.html',{'data':res})

def search_acntsub(request):
    button=request.POST['button']
    if button == 'Search':
        txt=request.POST['text']
        res = account_sub.objects.filter(account_sub_name__icontains=txt)
        return render(request, 'Accountant/View AccountSub.html', {'data': res})
    else:
        frm=request.POST['from']
        to=request.POST['to']
        res = account_sub.objects.filter(date__range=[frm, to])
        return render(request, 'Accountant/View AccountSub.html', {'data': res})

def View_profile_ac(request):
    res=staff.objects.get(LOGIN=request.session["lid"])
    return render(request, 'Accountant/View Profile.html',{'data':res})

def View_project_payment_entry_ac(request,id):
    res=payemnt_entry.objects.filter(PROJECT=id)
    res2 = project.objects.get(id=id, status='ongoing')
    return render(request, 'Accountant/View Project Payment Entry.html',{'data':res2,'data1':res,'id':id})

def search_pymtey(request):
    id=request.POST['pid']
    PROJECT = project.objects.get(id=id)
    frm=request.POST['from']
    to=request.POST['to']
    res = payemnt_entry.objects.filter(date__range=[frm,to],PROJECT=PROJECT)
    res2 = project.objects.get(id=id, status='ongoing')
    return render(request, 'Accountant/View Project Payment Entry.html', {'data': res2,'data1':res, 'id': id})

def View_Project_statusac(request,id):
    res=work_progress.objects.filter(PROJECT=id)
    res2 = project.objects.get(id=id, status='ongoing')
    l = []
    for i in res:
        ws = schedule.objects.filter(WORK=i.WORK, PROJECT=i.PROJECT)
        if ws.exists():
            a = ws[0].to_date
            import datetime
            to_date = datetime.datetime.strftime(a, '%Y-%m-%d')
            today = datetime.datetime.now().strftime("%Y-%m-%d")
            if to_date > today:
                ss = "ok"
                from datetime import datetime as dt
                res = (dt.strptime(to_date, "%Y-%m-%d") - dt.strptime(today, "%Y-%m-%d")).days
                if res < 3:
                    ss = "not"
                    if i.status == "Completed":
                        ss = "ok"
                else:
                    ss = "ok"
            else:
                if i.status == "Completed":
                    ss = "ok"
                else:
                    ss = "no"
            l.append({'ss': ss, 'WORK': i.WORK, 'date': i.date, 'status': i.status, 'progress': i.progress,'todate': to_date})
    return render(request, 'Accountant/View Project Status.html',{'data':res2,'data1':l,'id':id})

def search_prstac(request):
    button=request.POST['button']
    if button == 'Search':
        id = request.POST['pid']
        p = project.objects.get(id=id)
        txt=request.POST['text']
        res = work_progress.objects.filter(PROJECT=p,WORK__workname__icontains=txt)
        res2 = project.objects.get(id=id, status='ongoing')
        l = []
        for i in res:
            ws = schedule.objects.filter(WORK=i.WORK, PROJECT=i.PROJECT)
            if ws.exists():
                a = ws[0].to_date
                import datetime
                to_date = datetime.datetime.strftime(a, '%Y-%m-%d')
                today = datetime.datetime.now().strftime("%Y-%m-%d")
                if to_date > today:
                    ss = "ok"
                    from datetime import datetime as dt
                    res = (dt.strptime(to_date, "%Y-%m-%d") - dt.strptime(today, "%Y-%m-%d")).days
                    if res < 3:
                        ss = "not"
                        if i.status == "Completed":
                            ss = "ok"
                    else:
                        ss = "ok"
                else:
                    if i.status == "Completed":
                        ss = "ok"
                    else:
                        ss = "no"
                l.append({'ss': ss, 'WORK': i.WORK, 'date': i.date, 'status': i.status, 'progress': i.progress,'todate': to_date})
        return render(request, 'Accountant/View Project Status.html', {'data': res2,'data1':l, 'id': id})
    else:
        id = request.POST['pid']
        p = project.objects.get(id=id)
        frm=request.POST['from']
        to=request.POST['to']
        res = work_progress.objects.filter(PROJECT=p,date__range=[frm,to])
        res2 = project.objects.get(id=id, status='ongoing')
        l = []
        for i in res:
            ws = schedule.objects.filter(WORK=i.WORK, PROJECT=i.PROJECT)
            if ws.exists():
                a = ws[0].to_date
                import datetime
                to_date = datetime.datetime.strftime(a, '%Y-%m-%d')
                today = datetime.datetime.now().strftime("%Y-%m-%d")
                if to_date > today:
                    ss = "ok"
                    from datetime import datetime as dt
                    res = (dt.strptime(to_date, "%Y-%m-%d") - dt.strptime(today, "%Y-%m-%d")).days
                    if res < 3:
                        ss = "not"
                        if i.status == "Completed":
                            ss = "ok"
                    else:
                        ss = "ok"
                else:
                    if i.status == "Completed":
                        ss = "ok"
                    else:
                        ss = "no"
                l.append({'ss': ss, 'WORK': i.WORK, 'date': i.date, 'status': i.status, 'progress': i.progress,'todate': to_date})
        return render(request, 'Accountant/View Project Status.html', {'data': res2,'data1':l, 'id': id})

def View_all_projects(request):
    res=project.objects.all()
    return render(request, 'Accountant/View All Projects.html',{'data':res})

def search_allprjtsac(request):
    button=request.POST['button']
    if button == 'Search':
        txt=request.POST['text']
        res = project.objects.filter(project_name__icontains=txt)
        return render(request, 'Accountant/View All Projects.html', {'data': res})
    else:
        frm=request.POST['from']
        to=request.POST['to']
        res = project.objects.filter(date__range=[frm,to])
        return render(request, 'Accountant/View All Projects.html', {'data': res})

def View_projects(request):
    res=project.objects.filter(status='ongoing')
    return render(request, 'Accountant/View Projects.html',{'data':res})

def search_prjtsac(request):
    button=request.POST['button']
    if button == 'Search':
        txt=request.POST['text']
        res = project.objects.filter(status='ongoing',project_name__icontains=txt)
        return render(request, 'Accountant/View Projects.html', {'data': res})
    else:
        frm=request.POST['from']
        to=request.POST['to']
        res = project.objects.filter(status='ongoing',date__range=[frm,to])
        return render(request, 'Accountant/View Projects.html', {'data': res})

@legacy_role_required('Accountant')
def View_projects_functionsac(request,id):
    selected = get_object_or_404(project, id=id, status='ongoing')
    return render(request, 'Accountant/View Projects Functions.html', {
        'data': selected,
        'project_managers': project_manager_allocation.objects.filter(PROJECT=selected).select_related('STAFF'),
        'scope_rows': work.objects.filter(PROJECT=selected),
        'material_rows': material_required.objects.filter(PROJECT=selected).select_related('MATERIAL'),
        'estimate_rows': estimate.objects.filter(PROJECT=selected),
        'subcontractor_rows': subcotractor_project_allocation.objects.filter(PROJECT=selected).select_related('SUBCONTRACTOR'),
        'schedule_rows': schedule.objects.filter(PROJECT=selected).select_related('WORK'),
        'material_request_rows': material_request.objects.filter(PROJECT=selected).select_related('MATERIAL'),
        'payment_rows': payemnt_entry.objects.filter(PROJECT=selected),
        'inspection_rows': inspection.objects.filter(PROJECT=selected),
        'issued_rows': material_issued.objects.filter(PROJECT=selected).select_related('MATERIAL', 'STAFF'),
        'drawing_rows': drawing.objects.filter(PROJECT=selected),
        'document_rows': documents.objects.filter(PROJECT=selected),
        'workflow_document_rows': project_document.objects.filter(transferred_to=selected),
        'quotation_rows': quotation.objects.filter(ENQUIRY__PROJECT=selected, status='accepted').select_related('ENQUIRY'),
        'purchaser_rows': purchaser_project_allocation.objects.filter(PROJECT=selected).select_related('STAFF'),
        'progress_rows': work_progress.objects.filter(PROJECT=selected).select_related('WORK'),
        'usage_rows': material_usage.objects.filter(PROJECT=selected).select_related('MATERIAL', 'STAFF'),
    })

def View_Completed_projects(request):
    res=project.objects.filter(status='Completed')
    return render(request, 'Accountant/View Completed Projects.html',{'data':res})

def search_prjtscdac(request):
    button=request.POST['button']
    if button == 'Search':
        txt=request.POST['text']
        res = project.objects.filter(status='completed',project_name__icontains=txt)
        return render(request, 'Accountant/View Completed Projects.html', {'data': res})
    else:
        frm=request.POST['from']
        to=request.POST['to']
        res = project.objects.filter(status='completed',date__range=[frm,to])
        return render(request, 'Accountant/View Completed Projects.html', {'data': res})

def View_transaction_entry(request):
    res=transaction.objects.all()
    return render(request, 'Accountant/View Transaction Entry.html',{'data':res})

def search_tnct(request):
    button=request.POST['button']
    if button == 'Search':
        txt=request.POST['text']
        res = transaction.objects.filter(title__icontains=txt)
        return render(request, 'Accountant/View Transaction Entry.html', {'data': res})
    else:
        frm=request.POST['from']
        to=request.POST['to']
        res = transaction.objects.filter(date__range=[frm,to])
        return render(request, 'Accountant/View Transaction Entry.html', {'data': res})

######################################################PURCHASER#########################################

def pchome(request):
    return render(request,'Purchaser/pcindex.html')

def view_assigned_projectspc(request):
    p=purchaser_project_allocation.objects.filter(STAFF=request.session['sid'])
    return render(request,'Purchaser/View Assigned Projects.html',{'data':p})

def search_asppc(request):
    button=request.POST['button']
    if button == 'Search':
        txt=request.POST['text']
        res = supervisor_allocation.objects.filter(STAFF=request.session["sid"],PROJECT__project_name__icontains=txt)
        return render(request, 'Purchaser/View Assigned Projects.html', {'data': res, 'id': id})
    else:
        frm=request.POST['from']
        to=request.POST['to']
        res = supervisor_allocation.objects.filter(STAFF=request.session["sid"],PROJECT__date__range=[frm,to])
        return render(request, 'Purchaser/View Assigned Projects.html', {'data': res, 'id': id})

def view_completed_projectspc(request):
    p=purchaser_project_allocation(STAFF=request.session['sid'],PROJECT__status='Completed')
    return render(request,'Purchaser/View Completed Projects.html',{'data':p})

def search_aspcdpc(request):
    button=request.POST['button']
    if button == 'Search':
        txt=request.POST['text']
        res = purchaser_project_allocation.objects.filter(STAFF=request.session["sid"],PROJECT__status='completed',PROJECT__project_name__icontains=txt)
        return render(request, 'Purchaser/View Completed Projects.html', {'data': res, 'id': id})
    else:
        frm=request.POST['from']
        to=request.POST['to']
        res = purchaser_project_allocation.objects.filter(STAFF=request.session["sid"],PROJECT__status='completed',PROJECT__date__range=[frm,to])
        return render(request, 'Purchaser/View Completed Projects.html', {'data': res, 'id': id})

def view_ongoing_projectpc(request):
    p=purchaser_project_allocation.objects.filter(PROJECT__status='ongoing',STAFF=request.session["sid"])
    return render(request,'Purchaser/View Ongoing Project.html',{'data':p})

def search_ongppc(request):
    button=request.POST['button']
    if button == 'Search':
        txt=request.POST['text']
        res = purchaser_project_allocation.objects.filter(status='ongoing',STAFF=request.session["sid"],PROJECT__project_name__icontains=txt)
        return render(request, 'Purchaser/View Ongoing Project.html', {'data': res})
    else:
        frm=request.POST['from']
        to=request.POST['to']
        res = purchaser_project_allocation.objects.filter(status='ongoing',STAFF=request.session["sid"],PROJECT__date__range=[frm,to])
        return render(request, 'Purchaser/View Ongoing Project.html', {'data': res})

def View_projects_functionspr(request,id):
    res = purchaser_project_allocation.objects.get(PROJECT=id, PROJECT__status='ongoing', STAFF=request.session["sid"])
    return render(request,'Purchaser/View Ongoing Projects Functions.html',{'data':res})

def view_profilepc(request):
    res=staff.objects.get(LOGIN=request.session['sid'])
    return render(request,'Purchaser/View Profile.html',{'data':res})

def Change_password_pc(request):
    return render(request,'Purchaser/Change Password.html')

def Change_password_pc_post(request):
    return _change_session_password(request, '/WMS/Change_password_pc/')

def View_material_requiredpc(request,id):
    res=material_required.objects.filter(PROJECT=id)
    res2 = purchaser_project_allocation.objects.get(PROJECT=id,PROJECT__status='ongoing', STAFF=request.session["sid"])
    return render(request, 'Purchaser/View Materials Required.html',{'data':res2,'data1':res,'id':id})

def search_mrdpc(request):
    id = request.POST['id']
    p=project.objects.get(pk=id)
    txt = request.POST['text']
    res = material_required.objects.filter(MATERIAL__name__icontains=txt,PROJECT=p)
    res2 = purchaser_project_allocation.objects.get(PROJECT=id,PROJECT__status='ongoing', STAFF=request.session["sid"])
    return render(request, 'Purchaser/View Materials Required.html', {'data': res2,'data1':res,'id':id})

def View_materials_requestpc(request,id):
    res=material_request.objects.filter(PROJECT=id)
    res2 = purchaser_project_allocation.objects.get(PROJECT=id, PROJECT__status='ongoing', STAFF=request.session["sid"])
    return render(request, 'Purchaser/View Material Request.html',{'data':res2,'data1':res,'id':id})

def search_mrtpc(request):
    button = request.POST['button']
    if button == 'Search':
        id = request.POST['pid']
        p = project.objects.get(pk=id)
        txt = request.POST['text']
        res = material_request.objects.filter(PROJECT=p, MATERIAL__name__icontains=txt)
        res2 = purchaser_project_allocation.objects.get(PROJECT=id, PROJECT__status='ongoing',STAFF=request.session["sid"])
        return render(request, 'Purchaser/View Material Request.html', {'data': res2,'data1':res, 'id': id})
    else:
        id = request.POST['pid']
        p = project.objects.get(pk=id)
        frm = request.POST['from']
        to = request.POST['to']
        res = material_request.objects.filter(PROJECT=p, date__range=[frm, to])
        res2 = purchaser_project_allocation.objects.get(PROJECT=id, PROJECT__status='ongoing',STAFF=request.session["sid"])
        return render(request, 'Purchaser/View Material Request.html', {'data': res2,'data1':res, 'id': id})

def View_delivered_materials(request,id):
    res=material_delivery.objects.filter(MATERIAL_ISSUED__PROJECT=id)
    return render(request, 'Purchaser/View Materials Delivered.html',{'data':res,'id':id})

def search_deld(request):
    button = request.POST['button']
    if button == 'Search':
        id = request.POST['pid']
        p = project.objects.get(pk=id)
        txt = request.POST['text']
        res = material_delivery.objects.filter(PROJECT=p,MATERIAL__name__icontains=txt)
        return render(request, 'Purchaser/View Materials Delivered.html', {'data': res, 'id': id})
    else:
        id = request.POST['pid']
        p = project.objects.get(pk=id)
        frm = request.POST['from']
        to = request.POST['to']
        res = material_delivery.objects.filter(PROJECT=p,date__range=[frm, to])
        return render(request, 'Purchaser/View Materials Delivered.html', {'data': res, 'id': id})

def View_material_issuedpc(request,id):
    res=material_issued.objects.filter(PROJECT=id)
    res2 = purchaser_project_allocation.objects.get(PROJECT=id, PROJECT__status='ongoing', STAFF=request.session["sid"])
    return render(request, 'Purchaser/View Materials Issued.html',{'data':res2,'data1':res,'id':id})

def Update_issue_statuspc(request,id):
    material_issued.objects.filter(pk=id).update(status='delivered')
    return HttpResponse("<script>alert('Updated');window.location='/WMS/View_material_issuedpc/"+id+"#myid'</script>")

def search_misdpc(request):
    button = request.POST['button']
    if button == 'Search':
        id = request.POST['pid']
        p = project.objects.get(pk=id)
        txt = request.POST['text']
        res = material_issued.objects.filter(PROJECT=p,MATERIAL__name__icontains=txt)

        res2 = purchaser_project_allocation.objects.get(PROJECT=id, PROJECT__status='ongoing',STAFF=request.session["sid"])
        return render(request, 'Purchaser/View Materials Issued.html', {'data': res2,'data1':res, 'id': id})
    else:
        id = request.POST['pid']
        p = project.objects.get(pk=id)
        frm = request.POST['from']
        to = request.POST['to']
        res = material_issued.objects.filter(PROJECT=p,date__range=[frm, to])
        res2 = purchaser_project_allocation.objects.get(PROJECT=id, PROJECT__status='ongoing',STAFF=request.session["sid"])
        return render(request, 'Purchaser/View Materials Issued.html', {'data': res2,'data1':res, 'id': id})

def View_work_progresspc(request,id):
    res=work_progress.objects.filter(PROJECT=id)
    res2 = purchaser_project_allocation.objects.get(PROJECT=id, PROJECT__status='ongoing', STAFF=request.session["sid"])
    l = []
    for i in res:
        ws = schedule.objects.filter(WORK=i.WORK, PROJECT=i.PROJECT)
        if ws.exists():
            a = ws[0].to_date
            import datetime
            to_date = datetime.datetime.strftime(a, '%Y-%m-%d')
            today = datetime.datetime.now().strftime("%Y-%m-%d")
            if to_date > today:
                ss = "ok"
                from datetime import datetime as dt
                res = (dt.strptime(to_date, "%Y-%m-%d") - dt.strptime(today, "%Y-%m-%d")).days
                if res < 3:
                    ss = "not"
                    if i.status == "Completed":
                        ss = "ok"
                else:
                    ss = "ok"
            else:
                if i.status == "Completed":
                    ss = "ok"
                else:
                    ss = "no"
            l.append({'ss': ss, 'WORK': i.WORK, 'date': i.date, 'status': i.status, 'progress': i.progress,'todate': to_date})
    return render(request, 'Purchaser/View work progress.html',{'data':res2,'data1':l,'id':id})

def search_prstapc(request):
    button=request.POST['button']
    if button == 'Search':
        id = request.POST['pid']
        p = project.objects.get(id=id)
        txt=request.POST['text']
        res = work_progress.objects.filter(PROJECT=p,WORK__workname__icontains=txt)
        res2 = purchaser_project_allocation.objects.get(PROJECT=id, PROJECT__status='ongoing',STAFF=request.session["sid"])
        l = []
        for i in res:
            ws = schedule.objects.filter(WORK=i.WORK, PROJECT=i.PROJECT)
            if ws.exists():
                a = ws[0].to_date
                import datetime
                to_date = datetime.datetime.strftime(a, '%Y-%m-%d')
                today = datetime.datetime.now().strftime("%Y-%m-%d")
                if to_date > today:
                    ss = "ok"
                    from datetime import datetime as dt
                    res = (dt.strptime(to_date, "%Y-%m-%d") - dt.strptime(today, "%Y-%m-%d")).days
                    if res < 3:
                        ss = "not"
                        if i.status == "Completed":
                            ss = "ok"
                    else:
                        ss = "ok"
                else:
                    if i.status == "Completed":
                        ss = "ok"
                    else:
                        ss = "no"
                l.append({'ss': ss, 'WORK': i.WORK, 'date': i.date, 'status': i.status, 'progress': i.progress,'todate': to_date})
        return render(request, 'Purchaser/View work progress.html', {'data': res2,'data1':l, 'id': id})
    else:
        id = request.POST['pid']
        p = project.objects.get(id=id)
        frm=request.POST['from']
        to=request.POST['to']
        res = work_progress.objects.filter(PROJECT=p,date__range=[frm,to])
        res2 = purchaser_project_allocation.objects.get(PROJECT=id, PROJECT__status='ongoing',STAFF=request.session["sid"])
        l = []
        for i in res:
            ws = schedule.objects.filter(WORK=i.WORK, PROJECT=i.PROJECT)
            if ws.exists():
                a = ws[0].to_date
                import datetime
                to_date = datetime.datetime.strftime(a, '%Y-%m-%d')
                today = datetime.datetime.now().strftime("%Y-%m-%d")
                if to_date > today:
                    ss = "ok"
                    from datetime import datetime as dt
                    res = (dt.strptime(to_date, "%Y-%m-%d") - dt.strptime(today, "%Y-%m-%d")).days
                    if res < 3:
                        ss = "not"
                        if i.status == "Completed":
                            ss = "ok"
                    else:
                        ss = "ok"
                else:
                    if i.status == "Completed":
                        ss = "ok"
                    else:
                        ss = "no"
                l.append({'ss': ss, 'WORK': i.WORK, 'date': i.date, 'status': i.status, 'progress': i.progress,'todate': to_date})
        return render(request, 'Purchaser/View work progress.html', {'data': res2,'data1':l, 'id': id})

def deliver_materials(request,id):
    res=material_issued.objects.get(pk=id)
    return render(request,'Purchaser/Deliver Materials to Site.html',{'data':res})

def deliver_materials_post(request):
    id=request.POST['id']
    mid=request.POST['mid']
    m=material_issued.objects.get(pk=mid)
    quantity=request.POST['quantity']
    # unit=request.POST['unit']
    supplier=request.POST['supplier']
    place=request.POST['place']
    pid=request.session["sid"]
    p=staff.objects.get(pk=pid)
    from datetime import datetime
    date=datetime.now().strftime("%Y-%m-%d")

    dlry=material_delivery()
    dlry.MATERIAL_ISSUED=m
    dlry.quantity=quantity
    # dlry.unit=unit
    dlry.supplier=supplier
    dlry.place=place
    dlry.date=date
    dlry.PURCHASER=p
    dlry.save()
    return HttpResponse("<script>alert('Added Successfully');window.location='/WMS/View_material_issuedpc/"+id+"'</script>")

def Edit_delivered_materials(request,id):
    res=material_delivery.objects.get(pk=id)
    return render(request,'Purchaser/Edit Delivered Materials.html',{'data':res})

def Edit_delivered_materials_post(request):
    eid=request.POST['eid']
    pid=request.POST['pid']
    quantity=request.POST['quantity']
    # unit=request.POST['unit']
    supplier=request.POST['supplier']
    place=request.POST['place']
    material_delivery.objects.filter(pk=eid).update(quantity=quantity,supplier=supplier,place=place)
    return HttpResponse("<script>alert('Edited Successfully');window.location='/WMS/View_delivered_materials/"+pid+"'</script>")

def Delete_drdm(request,id,pid):
    material_delivery.objects.filter(pk=id).delete()
    return HttpResponse("<script>alert('Deleted Successfully');window.location='/WMS/View_delivered_materials/"+pid+"'</script>")

def Delete_chatpc(request,id,pid):
    lid=request.session['lid']
    chat.objects.filter(id=id, LOGIN_id=lid).delete()
    p=project.objects.get(id=pid).project_name
    return render(request,'Purchaser/fur_chat.html', {'id':pid,'lid':lid,'p':p})

def chatspc(request,id,msg):
    lid=str(request.session['lid'])
    from datetime import datetime

    sender = staff.objects.get(LOGIN_id=lid)

    d=chat()
    d.LOGIN_id=lid
    d.PROJECT_id=id
    d.message=msg
    d.date=datetime.now().strftime("%Y-%m-%d")
    d.time=datetime.now().strftime("%I:%M %p")
    d.type=sender.name+" , "+sender.designation
    d.save()
    return JsonResponse({'status':'ok'})

def chatpc(request,id):
    lid=request.session['lid']
    p=project.objects.get(id=id).project_name
    return render(request,'Purchaser/fur_chat.html', {'id':id,'lid':lid,'p':p})

def viewmsg_pc(request,id):
    return JsonResponse({'data': _chat_messages(id, request.session['lid'])})

def View_notification_ajax(request):
    allocated_project_ids = project_manager_allocation.objects.filter(
        STAFF=request.session["sid"]
    ).values_list('PROJECT_id', flat=True)
    nt = notification.objects.filter(
        PROJECT_id__in=allocated_project_ids,
        status='pending',
    ).values('PROJECT_id').distinct().count()
    return JsonResponse({'status':'ok','nt':nt})








