from django.urls import path

from . import views


app_name = 'mobile_api'

urlpatterns = [
    path('auth/login/', views.LoginView.as_view(), name='login'),
    path('auth/logout/', views.LogoutView.as_view(), name='logout'),
    path('me/', views.MeView.as_view(), name='me'),
    path('dashboard/', views.DashboardView.as_view(), name='dashboard'),
    path('materials/', views.MaterialListView.as_view(), name='materials'),
    path('projects/', views.ProjectListView.as_view(), name='projects'),
    path('projects/<int:project_id>/', views.ProjectDetailView.as_view(), name='project-detail'),
    path('projects/<int:project_id>/chat/', views.ProjectChatView.as_view(), name='project-chat'),
    path('projects/<int:project_id>/site-updates/', views.SiteUpdateView.as_view(), name='site-updates'),
    path('material-requests/<int:request_id>/<str:decision>/', views.MaterialRequestDecisionView.as_view(), name='material-request-decision'),
    path('notifications/', views.NotificationListView.as_view(), name='notifications'),
    path('notifications/<int:notification_id>/read/', views.NotificationReadView.as_view(), name='notification-read'),
    path('enquiries/', views.EnquiryListView.as_view(), name='enquiries'),
    path('enquiries/<int:enquiry_id>/', views.EnquiryDetailView.as_view(), name='enquiry-detail'),
    path('enquiries/<int:enquiry_id>/comments/', views.EnquiryCommentView.as_view(), name='enquiry-comment'),
    path('enquiries/<int:enquiry_id>/actions/<str:action>/', views.EnquiryActionView.as_view(), name='enquiry-action'),
]
