import tempfile

from django.db import IntegrityError, transaction
from django.contrib.auth.hashers import check_password, make_password
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase
from django.urls import reverse

from .models import (
    chat, enquiry, enquiry_attachment, estimate, login, material, material_request,
    material_required, project, project_manager_allocation, quotation, schedule, staff,
    supervisor_allocation, work, work_progress,
)


class WorkflowTests(TestCase):
    def create_user(self, role, index):
        account = login.objects.create(
            username=f'user{index}@example.com', password='test-password', usertype=role
        )
        person = staff.objects.create(
            LOGIN=account, name=role, dob='', phone=f'90000000{index:02d}',
            email=account.username, photo='', place='', nation='', phone2='', designation=role,
        )
        return account, person

    def sign_in_as(self, account, person):
        session = self.client.session
        session['lid'] = account.pk
        session['sid'] = person.pk
        session.save()

    def setUp(self):
        self.executive = self.create_user('Marketing Executive', 1)
        self.manager = self.create_user('Marketing Manager', 2)
        self.estimator = self.create_user('Estimator', 3)
        self.accountant = self.create_user('Accountant', 4)
        self.project_manager = self.create_user('Project Manager', 5)
        self.controller = self.create_user('Document Controller', 6)

    def test_staff_email_is_unique(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            login.objects.create(username=self.executive[0].username, password='x', usertype='Estimator')

    def test_legacy_password_is_upgraded_after_login(self):
        response = self.client.post(reverse('login_post'), {
            'username': self.executive[0].username, 'password': 'test-password',
        })
        self.assertRedirects(response, reverse('workflow_dashboard'))
        self.executive[0].refresh_from_db()
        self.assertTrue(check_password('test-password', self.executive[0].password))

    def test_complete_quotation_approval_and_award_flow(self):
        self.sign_in_as(*self.executive)
        response = self.client.post(reverse('workflow_add_enquiry'), {
            'title': 'Office fit-out', 'client_name': 'Example Client',
            'client_email': 'client@example.com', 'description': 'Fit-out scope',
        })
        record = enquiry.objects.get()
        self.assertRedirects(response, reverse('workflow_detail', args=(record.pk,)))

        self.sign_in_as(*self.manager)
        response = self.client.post(reverse('workflow_assign', args=(record.pk,)), {
            'estimator': self.estimator[1].pk,
        })
        self.assertEqual(response.status_code, 302)

        self.sign_in_as(*self.estimator)
        response = self.client.post(reverse('workflow_add_quotation', args=(record.pk,)), {
            'amount': '12500.00', 'details': 'Version one',
            'material_cost': '5000', 'labour_cost': '3000', 'other_cost': '500',
        })
        self.assertEqual(response.status_code, 302)
        quote = quotation.objects.get()
        self.assertEqual(quote.status, 'manager_review')
        self.assertEqual(quote.costing.total, 8500)

        self.sign_in_as(*self.manager)
        self.assertEqual(
            self.client.get(reverse('workflow_detail', args=(record.pk,))).status_code, 200
        )
        self.client.post(reverse('workflow_manager_approve', args=(quote.pk,)))
        quote.refresh_from_db()
        self.assertEqual(quote.status, 'accountant_review')

        self.sign_in_as(*self.accountant)
        self.client.post(reverse('workflow_accountant_approve', args=(quote.pk,)))
        quote.refresh_from_db()
        self.assertEqual(quote.status, 'approved')

        self.sign_in_as(*self.project_manager)
        self.client.post(reverse('workflow_approve_costing', args=(quote.pk,)))
        quote.costing.refresh_from_db()
        self.assertIsNotNone(quote.costing.approved_at)

        self.sign_in_as(*self.controller)
        self.client.post(reverse('workflow_submit_quotation', args=(quote.pk,)))
        quote.refresh_from_db()
        self.assertEqual(quote.status, 'submitted')

        self.sign_in_as(*self.executive)
        self.client.post(reverse('workflow_award_project', args=(quote.pk,)))
        quote.refresh_from_db()
        record.refresh_from_db()
        self.assertEqual(quote.status, 'accepted')
        self.assertEqual(record.status, 'awarded')

    def test_estimator_cannot_view_unassigned_enquiry(self):
        record = enquiry.objects.create(
            title='Restricted', client_name='Client', created_by=self.executive[0]
        )
        self.sign_in_as(*self.estimator)
        response = self.client.get(reverse('workflow_detail', args=(record.pk,)))
        self.assertEqual(response.status_code, 403)
        response = self.client.post(reverse('workflow_add_comment', args=(record.pk,)), {'comment': 'No access'})
        self.assertEqual(response.status_code, 403)
        self.assertFalse(record.comments.exists())

    def test_quotation_rejects_non_finite_amounts(self):
        record = enquiry.objects.create(
            title='Invalid costing', client_name='Client', created_by=self.executive[0],
            assigned_to=self.estimator[1], status='assigned',
        )
        self.sign_in_as(*self.estimator)
        response = self.client.post(reverse('workflow_add_quotation', args=(record.pk,)), {
            'amount': 'NaN', 'material_cost': 'Infinity',
            'labour_cost': '0', 'other_cost': '0',
        })
        self.assertEqual(response.status_code, 302)
        self.assertFalse(quotation.objects.filter(ENQUIRY=record).exists())

    def test_cad_viewer_and_file_are_private_to_authorized_users(self):
        with tempfile.TemporaryDirectory() as media_root, self.settings(MEDIA_ROOT=media_root):
            record = enquiry.objects.create(
                title='CAD enquiry', client_name='Client', created_by=self.executive[0]
            )
            attachment = enquiry_attachment.objects.create(
                ENQUIRY=record,
                original_name='Ground Floor Plan.dxf',
                file=SimpleUploadedFile('Ground Floor Plan.dxf', b'0\nSECTION\n0\nEOF\n'),
            )

            self.sign_in_as(*self.executive)
            viewer = self.client.get(
                reverse('workflow_cad_viewer', args=('enquiry', attachment.pk))
            )
            self.assertEqual(viewer.status_code, 200)
            self.assertContains(viewer, 'Ground Floor Plan.dxf')

            drawing = self.client.get(
                reverse('workflow_cad_file', args=('enquiry', attachment.pk))
            )
            self.assertEqual(drawing.status_code, 200)
            self.assertEqual(b''.join(drawing.streaming_content), b'0\nSECTION\n0\nEOF\n')
            self.assertIn('private', drawing['Cache-Control'])

            self.sign_in_as(*self.estimator)
            denied = self.client.get(
                reverse('workflow_cad_viewer', args=('enquiry', attachment.pk))
            )
            self.assertEqual(denied.status_code, 403)


class BulkPlanningTests(TestCase):
    def create_project(self, number, name):
        return project.objects.create(
            project_no=number, project_name=name, client_name='Client', phone=9000000000,
            email='client@example.com', place='Dubai', unit_no='', project_value='1000',
            start_date='2026-07-01', handout_date='2026-08-01', project_duration='31 Days',
            project_area='', project_type='', description='', date='2026-07-01',
            estimate_status='pending', status='pending',
        )

    def setUp(self):
        account = login.objects.create(
            username='planner@example.com', password='test-password', usertype='Project Manager'
        )
        person = staff.objects.create(
            LOGIN=account, name='Planner', dob='', phone='9000000099', email=account.username,
            photo='', place='', nation='', phone2='', designation='Project Manager',
        )
        session = self.client.session
        session['lid'] = account.pk
        session['sid'] = person.pk
        session['role'] = 'Project Manager'
        session.save()
        self.source = self.create_project('SRC-1', 'Source Project')
        self.target = self.create_project('DST-1', 'Target Project')
        self.cement = material.objects.create(name='Cement', unit='bag')
        self.paint = material.objects.create(name='Paint', unit='gallon')

    def test_legacy_wms_routes_require_login(self):
        response = Client().get(reverse('Add_material'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/WMS/login/', response.url)

    def test_bulk_scope_add_is_atomic_and_creates_schedules(self):
        response = self.client.post(reverse('Add_works_post'), {
            'id': str(self.target.pk), 'pid': str(self.target.pk),
            'category': ['Electrical', 'Painting'],
            'work': ['Install containment', 'Apply finish coat'],
            'start': ['2026-07-10', ''], 'end': ['2026-07-12', ''],
        })
        self.assertRedirects(
            response, reverse('View_work', args=(self.target.pk,)), fetch_redirect_response=False
        )
        self.assertEqual(work.objects.filter(PROJECT=self.target).count(), 2)
        self.assertEqual(schedule.objects.filter(PROJECT=self.target).count(), 1)
        self.assertEqual(work_progress.objects.filter(PROJECT=self.target).count(), 1)

        before = work.objects.filter(PROJECT=self.target).count()
        response = self.client.post(reverse('Add_works_post'), {
            'id': str(self.target.pk), 'pid': str(self.target.pk),
            'category': ['HVAC'], 'work': ['Invalid dates'],
            'start': ['2026-08-10'], 'end': ['2026-08-01'],
        })
        self.assertEqual(response.status_code, 400)
        self.assertEqual(work.objects.filter(PROJECT=self.target).count(), before)

    def test_bulk_material_requirements_and_source_fetch(self):
        material_required.objects.create(
            PROJECT=self.source, MATERIAL=self.cement, category='Preliminaries', quantity='25', price='20'
        )
        response = self.client.get(reverse('Project_list_data', args=(self.source.pk, 'materials')))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['rows'][0]['material_id'], self.cement.pk)

        response = self.client.post(reverse('Add_material_required_post'), {
            'pid': str(self.target.pk),
            'category': ['Preliminaries', 'Painting'],
            'material': [str(self.cement.pk), str(self.paint.pk)],
            'quantity': ['50', '10'], 'price': ['21.50', '45'],
        })
        self.assertRedirects(
            response, reverse('View_materials_required', args=(self.target.pk,)),
            fetch_redirect_response=False,
        )
        self.assertEqual(material_required.objects.filter(PROJECT=self.target).count(), 2)

    def test_scope_source_fetch_includes_schedule_dates(self):
        scope = work.objects.create(PROJECT=self.source, category='Electrical', workname='Install cables')
        schedule.objects.create(
            PROJECT=self.source, WORK=scope, from_date='2026-07-20', to_date='2026-07-25'
        )
        response = self.client.get(reverse('Project_list_data', args=(self.source.pk, 'scope')))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['rows'][0], {
            'category': 'Electrical', 'work': 'Install cables',
            'start': '2026-07-20', 'end': '2026-07-25',
        })

    def test_estimate_number_is_scoped_to_project(self):
        estimate.objects.create(PROJECT=self.source, est_no='EST-001', date='2026-07-01')
        response = self.client.post(reverse('Add_Requirement_Estimate_post'), {
            'pid': self.target.pk, 'pr': '0', 'm': '0', 'c': '0', 'est': 'EST-001',
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(estimate.objects.filter(est_no='EST-001').count(), 2)
        self.assertTrue(estimate.objects.filter(PROJECT=self.target, est_no='EST-001').exists())

    def test_material_request_edit_uses_project_materials_and_valid_fields(self):
        material_required.objects.create(
            PROJECT=self.target, MATERIAL=self.paint, category='Painting', quantity='10', price='45'
        )
        sender = staff.objects.get(email='planner@example.com')
        request_row = material_request.objects.create(
            PROJECT=self.target, MATERIAL=self.cement, STAFF=sender,
            quantity='2', date='2026-07-18',
        )
        response = self.client.get(reverse('Edit_material_request', args=(request_row.pk, self.target.pk)))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(list(response.context['data1']), list(material_required.objects.filter(PROJECT=self.target)))

        response = self.client.post(reverse('Edit_material_request_post'), {
            'pid': self.target.pk, 'mid': request_row.pk,
            'material': self.paint.pk, 'quantity': '4',
        })
        self.assertEqual(response.status_code, 200)
        request_row.refresh_from_db()
        self.assertEqual(request_row.MATERIAL, self.paint)
        self.assertEqual(request_row.quantity, '4')

    def test_admin_chat_uses_current_login(self):
        admin = login.objects.create(username='admin@example.com', password='x', usertype='Admin')
        session = self.client.session
        session['lid'] = admin.pk
        session['role'] = 'Admin'
        session.save()
        response = self.client.get(reverse('chatsa', args=(self.target.pk, 'hello')))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(chat.objects.get().LOGIN, admin)


class MobileApiTests(TestCase):
    def create_user(self, role, index):
        account = login.objects.create(
            username=f'mobile{index}@example.com',
            password=make_password('SecurePass123!'),
            usertype=role,
        )
        person = staff.objects.create(
            LOGIN=account, name=f'{role} Mobile', dob='', phone=f'80000000{index:02d}',
            email=account.username, photo='', place='Dubai', nation='', phone2='', designation=role,
        )
        return account, person

    def create_project(self, number):
        return project.objects.create(
            project_no=f'P-{number}', project_name=f'Project {number}', client_name='Client',
            phone=971500000000 + number, email=f'client{number}@example.com', place='Dubai',
            unit_no='1', project_value='100000', start_date='2026-07-01',
            handout_date='2026-12-01', project_duration='5 months', project_area='1000 sq ft',
            project_type='Fit-out', description='Mobile API test', date='2026-07-01',
            estimate_status='approved', status='ongoing',
        )

    def token_for(self, account):
        response = self.client.post(
            reverse('mobile_api:login'),
            {'email': account.username, 'password': 'SecurePass123!'},
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        return response.json()['token']

    def api_headers(self, account):
        return {'HTTP_AUTHORIZATION': f'Bearer {self.token_for(account)}'}

    def setUp(self):
        self.supervisor = self.create_user('Supervisor', 1)
        self.manager = self.create_user('Project Manager', 2)
        self.marketing = self.create_user('Marketing Executive', 3)
        self.assigned = self.create_project(1)
        self.unassigned = self.create_project(2)
        supervisor_allocation.objects.create(
            allocated_date='2026-07-19', PROJECT=self.assigned, STAFF=self.supervisor[1]
        )
        project_manager_allocation.objects.create(
            allocated_date='2026-07-19', PROJECT=self.assigned, STAFF=self.manager[1]
        )
        self.material = material.objects.create(name='Cement', unit='bag')

    def test_mobile_api_requires_bearer_authentication(self):
        response = self.client.get(reverse('mobile_api:dashboard'))
        self.assertEqual(response.status_code, 401)
        self.assertIn('error', response.json())

    def test_login_and_role_filtered_projects(self):
        response = self.client.get(reverse('mobile_api:projects'), **self.api_headers(self.supervisor[0]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual([row['id'] for row in response.json()['results']], [self.assigned.pk])

    def test_supervisor_can_submit_site_material_request(self):
        response = self.client.post(
            reverse('mobile_api:site-updates', args=(self.assigned.pk,)),
            {'type': 'material_request', 'material_id': self.material.pk, 'quantity': '12'},
            content_type='application/json', **self.api_headers(self.supervisor[0]),
        )
        self.assertEqual(response.status_code, 201)
        self.assertTrue(material_request.objects.filter(PROJECT=self.assigned, quantity='12').exists())

    def test_project_manager_can_approve_material_request(self):
        item = material_request.objects.create(
            PROJECT=self.assigned, MATERIAL=self.material, STAFF=self.supervisor[1],
            quantity='5', date='2026-07-19', status='pending',
        )
        response = self.client.post(
            reverse('mobile_api:material-request-decision', args=(item.pk, 'approve')),
            **self.api_headers(self.manager[0]),
        )
        self.assertEqual(response.status_code, 200)
        item.refresh_from_db()
        self.assertEqual(item.status, 'approved')

    def test_marketing_user_can_create_and_comment_on_enquiry(self):
        headers = self.api_headers(self.marketing[0])
        response = self.client.post(
            reverse('mobile_api:enquiries'),
            {'title': 'New fit-out', 'client_name': 'Mobile Client', 'description': 'New request'},
            content_type='application/json', **headers,
        )
        self.assertEqual(response.status_code, 201)
        enquiry_id = response.json()['enquiry']['id']
        response = self.client.post(
            reverse('mobile_api:enquiry-comment', args=(enquiry_id,)),
            {'comment': 'Client requested an early estimate.'},
            content_type='application/json', **headers,
        )
        self.assertEqual(response.status_code, 201)
