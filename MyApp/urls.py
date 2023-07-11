
from django.contrib import admin
from django.urls import path,include

from .import views;

urlpatterns = [

    path('login/',views.loginn,name="login"),
    path('login_post/',views.login_post,name="login_post"),

     # ADMIN #
    path('Admin_home/', views.Admin_home, name="Admin_home"),
    path('Add_project/',views.Add_project,name="Add_project"),
    path('Add_project_post/',views.Add_project_post,name="Add_project_post"),
    path('Add_staff/',views.Add_staff,name="Add_staff"),
    path('Add_staff_post/',views.Add_staff_post,name="Add_staff_post"),
    path('Edit_Projec_allocation_to_pm/<str:id>',views.Edit_Projec_allocation_to_pm,name="Edit_Projec_allocation_to_pm"),
    path('Edit_Projec_allocation_to_pm_post/',views.Edit_Projec_allocation_to_pm_post,name="Edit_Projec_allocation_to_pm_post"),
    path('Delete_pma/<str:id>', views.Delete_pma, name="Delete_pma"),
    path('Edit_Projec_allocation_to_supervisor/<str:id>',views.Edit_Projec_allocation_to_supervisor,name="Edit_Projec_allocation_to_supervisor"),
    path('Edit_Projec_allocation_to_supervisor_post/', views.Edit_Projec_allocation_to_supervisor_post, name="Edit_Projec_allocation_to_supervisor_post"),
    path('Delete_psa/<str:id>', views.Delete_psa, name="Delete_psa"),
    path('Edit_project/<str:id>', views.Edit_project, name="Edit_project"),
    path('Edit_project_post/',views.Edit_project_post,name="Edit_project_post"),
    path('Delete_project/<str:id>', views.Delete_project, name="Delete_project"),
    path('Edit_staff/<str:id>', views.Edit_staff, name="Edit_staff"),
    path('Edit_staff_post/', views.Edit_staff_post, name="Edit_staff_post"),
    path('Delete_staff/<str:id>/<str:lid>', views.Delete_staff, name="Delete_staff"),
    path('Delete_chata/<str:id>/<str:pid>', views.Delete_chata, name="Delete_chata"),
    path('chatsa/<str:id>/<str:msg>', views.chatsa, name="chatsa"),
    path('chata/<str:id>', views.chata, name="chata"),
    path('viewmsg/<str:id>', views.viewmsg, name="viewmsg"),
    path('viewmsg_admin/<str:id>', views.viewmsg_admin, name="viewmsg_admin"),
    path('Projec_allocation_to_project_manager/<str:id>',views.Projec_allocation_to_project_manager,name="Projec_allocation_to_project_manager"),
    path('Projec_allocation_to_project_manager_post/',views.Projec_allocation_to_project_manager_post,name="Projec_allocation_to_project_manager_post"),
    path('Projec_allocation_to_supervisor/<str:id>',views.Projec_allocation_to_supervisor,name="Projec_allocation_to_supervisor"),
    path('Projec_allocation_to_supervisor_post/',views.Projec_allocation_to_supervisor_post,name="Projec_allocation_to_supervisor_post"),
    path('View_account_reports/',views.View_account_reports,name="View_account_reports"),
    path('search_acnts/', views.search_acnts, name="search_acnts"),
    path('View_all_subcontractors/',views.View_all_subcontractors,name="View_all_subcontractors"),
    path('search_sbcr/', views.search_sbcr, name="search_sbcr"),
    path('View_Budget/<str:id>',views.View_Budget,name="View_Budget"),
    path('search_bgta/', views.search_bgta, name="search_bgta"),
    path('View_Estimatead/<str:id>', views.View_Estimatead, name="View_Estimatead"),
    path('search_estad/', views.search_estad, name="search_estad"),
    path('approve_est/<str:id>', views.approve_est, name="approve_est"),
    path('reject_est/<str:id>', views.reject_est, name="reject_est"),
    path('View_Material_required/<str:id>',views.View_Material_required,name="View_Material_required"),
    path('search_msda/', views.search_msda, name="search_msda"),
    path('View_Ongoing_projects/',views.View_Ongoing_projects,name="View_Ongoing_projects"),
    path('search_prjcts/', views.search_prjcts, name="search_prjcts"),
    path('View_Payment_Entry/<str:id>',views.View_Payment_Entry,name="View_Payment_Entry"),
    path('search_pmnte/', views.search_pmnte, name="search_pmnte"),
    path('View_Project_allocated_to_project_manager/<str:id>',views.View_Project_allocated_to_project_manager,name="View_Project_allocated_to_project_manager"),
    path('search_pmr/', views.search_pmr, name="search_pmr"),
    path('View_Project_allocated_to_supervisor/<str:id>',views.View_Project_allocated_to_supervisor,name="View_Project_allocated_to_supervisor"),
    path('search_spra/', views.search_spra, name="search_spra"),
    path('View_Project/',views.View_Project,name="View_Project"),
    path('search_prjts/', views.search_prjts, name="search_prjts"),
    path('View_projects_functions/<str:id>', views.View_projects_functions, name="View_projects_functions"),
    path('View_Completed_Projects/', views.View_Completed_Projects, name="View_Completed_Projects"),
    path('search_prjtscd/', views.search_prjtscd, name="search_prjtscd"),
    path('View_Schedule/<str:id>',views.View_Schedule,name="View_Schedule"),
    path('schedule_searcha/',views.schedule_searcha,name="schedule_searcha"),
    path('View_Staff/',views.View_Staff,name="View_Staff"),
    path('search_staff/', views.search_staff, name="search_staff"),
    path('View_Subcontractor_datails_of_project/<str:id>',views.View_Subcontractor_datails_of_project,name="View_Subcontractor_datails_of_project"),
    path('search_sbcrp/', views.search_sbcrp, name="search_sbcrp"),
    path('View_Total_material_request/<str:id>',views.View_Total_material_request,name="View_Total_material_request"),
    path('search_mrqt/', views.search_mrqt, name="search_mrqt"),
    path('View_Total_worker_report/<str:id>',views.View_Total_worker_report,name="View_Total_worker_report"),
    path('search_twcr/', views.search_twcr, name="search_twcr"),
    path('View_Work_management/<str:id>', views.View_Work_management, name="View_Work_management"),
    path('search_worka/', views.search_worka, name="search_worka"),
    path('View_Work_progress/<str:id>', views.View_Work_progress, name="View_Work_progress"),
    path('search_prsta/', views.search_prsta, name="search_prsta"),
    path('View_Worksite_photos/<str:id>', views.View_Worksite_photos, name="View_Worksite_photos"),
    path('search_sp/', views.search_sp, name="search_sp"),

    #######################################################     #PROJECT MANAGER#  #######################################################

    path('PMHome/', views.PMHome, name="PMHome"),
    path('Add_Estimate/<str:id>', views.Add_Estimate, name="Add_Estimate"),
    path('Add_Estimate_post/', views.Add_Estimate_post, name="Add_Estimate_post"),
    path('Add_material_required/<str:id>', views.Add_material_required, name="Add_material_required"),
    path('Add_material_required_post/', views.Add_material_required_post, name="Add_material_required_post"),
    path('Add_material/', views.Add_material, name="Add_material"),
    path('Add_material_post/', views.Add_material_post, name="Add_material_post"),
    path('Add_project_inspection_details/<str:id>', views.Add_project_inspection_details, name="Add_project_inspection_details"),
    path('Add_project_inspection_details_post/', views.Add_project_inspection_details_post, name="Add_project_inspection_details_post"),
    path('Add_Requirement_Estimate/<str:id>/<str:pr>/<str:m>/<str:c>', views.Add_Requirement_Estimate, name="Add_Requirement_Estimate"),
    path('Add_Requirement_Estimate_post/', views.Add_Requirement_Estimate_post, name="Add_Requirement_Estimate_post"),
    path('Add_Subcontractor_Estimate/<str:id>/<str:amount>', views.Add_Subcontractor_Estimate, name="Add_Subcontractor_Estimate"),
    path('Add_Subcontractor_Estimate_post/', views.Add_Subcontractor_Estimate_post, name="Add_Subcontractor_Estimate_post"),
    path('Add_Subcontractor_schedule/<str:id>', views.Add_Subcontractor_schedule, name="Add_Subcontractor_schedule"),
    path('Add_Subcontractor_schedule_post/', views.Add_Subcontractor_schedule_post, name="Add_Subcontractor_schedule_post"),
    path('Add_Subcontractor_to_project/<str:id>', views.Add_Subcontractor_to_project,name="Add_Subcontractor_to_project"),
    path('Add_Subcontractor_to_project_post/', views.Add_Subcontractor_to_project_post, name="Add_Subcontractor_to_project_post"),
    path('Add_Subcontractor/', views.Add_Subcontractor,name="Add_Subcontractor"),
    path('Add_Subcontractor_post/', views.Add_Subcontractor_post, name="Add_Subcontractor_post"),
    path('Add_work_schedule/<str:id>', views.Add_work_schedule, name="Add_work_schedule"),
    path('Add_work_schedule_post/', views.Add_work_schedule_post, name="Add_work_schedule_post"),
    path('Add_works/<str:id>', views.Add_works, name="Add_works"),
    path('Add_works_post/', views.Add_works_post, name="Add_works_post"),
    path('Change_password/', views.Change_password, name="Change_password"),
    path('Change_password_post/', views.Change_password_post, name="Change_password_post"),
    path('Draft_budget/<str:id>', views.Draft_budget, name="Draft_budget"),
    path('Draft_budget_post/', views.Draft_budget_post, name="Draft_budget_post"),
    path('Exit_budget/', views.Exit_budget, name="Exit_budget"),
    path('Draft_Requirement_budget/<str:id>/<str:pr>/<str:m>/<str:c>', views.Draft_Requirement_budget, name="Draft_Requirement_budget"),
    path('Draft_Requirement_budget_post/', views.Draft_Requirement_budget_post, name="Draft_Requirement_budget_post"),
    path('Draft_Subcontractor_budget/<str:id>/<str:amnt>', views.Draft_Subcontractor_budget, name="Draft_Subcontractor_budget"),
    path('Draft_Subcontractor_budget_post/', views.Draft_Subcontractor_budget_post, name="Draft_Subcontractor_budget_post"),
    path('Edit_budget/<str:id>/<str:pid>', views.Edit_budget, name="Edit_budget"),
    path('Edit_budget_post/', views.Edit_budget_post, name="Edit_budget_post"),
    path('Delete_budget/<str:id>/<str:pid>', views.Delete_budget, name="Delete_budget"),
    path('Edit_Estimate/<str:id>/<str:pid>', views.Edit_Estimate, name="Edit_Estimate"),
    path('Edit_Estimate_post/', views.Edit_Estimate_post, name="Edit_Estimate_post"),
    path('Delete_Estimate/<str:id>/<str:pid>', views.Delete_Estimate, name="Delete_Estimate"),
    path('Edit_issued_materials_to_site/<str:id>/<str:pid>', views.Edit_issued_materials_to_site, name="Edit_issued_materials_to_site"),
    path('Edit_issued_materials_to_site_post/', views.Edit_issued_materials_to_site_post, name="Edit_issued_materials_to_site_post"),
    path('Delete_ismts/<str:id>/<str:pid>', views.Delete_ismts, name="Delete_ismts"),
    path('Edit_material_required/<str:id>/<str:pid>', views.Edit_material_required, name="Edit_material_required"),
    path('Edit_material_required_post/', views.Edit_material_required_post, name="Edit_material_required_post"),
    path('Delete_materialreqd/<str:id>/<str:pid>', views.Delete_materialreqd, name="Delete_materialreqd"),
    path('Edit_material/<str:id>', views.Edit_material, name="Edit_material"),
    path('Edit_material_post/', views.Edit_material_post, name="Edit_material_post"),
    path('Delete_material/<str:id>', views.Delete_material, name="Delete_material"),
    path('Edit_Projec_allocation_to_purchaser/<str:id>', views.Edit_Projec_allocation_to_purchaser, name="Edit_Projec_allocation_to_purchaser"),
    path('Edit_Projec_allocation_to_purchaser_post/', views.Edit_Projec_allocation_to_purchaser_post, name="Edit_Projec_allocation_to_purchaser_post"),
    path('Delete_pcal/<str:id>/<str:pid>', views.Delete_pcal, name="Delete_pcal"),
    path('Edit_project_inspection_details/<str:id>/<str:pid>', views.Edit_project_inspection_details, name="Edit_project_inspection_details"),
    path('Edit_project_inspection_details_post/', views.Edit_project_inspection_details_post, name="Edit_project_inspection_details_post"),
    path('Delete_inspection/<str:id>/<str:pid>', views.Delete_inspection, name="Delete_inspection"),
    path('Edit_Subcontractor_to_project/<str:id>/<str:pid>', views.Edit_Subcontractor_to_project, name="Edit_Subcontractor_to_project"),
    path('Edit_Subcontractor_to_project_post/', views.Edit_Subcontractor_to_project_post, name="Edit_Subcontractor_to_project_post"),
    path('Delete_subofpr/<str:id>/<str:pid>', views.Delete_subofpr, name="Delete_subofpr"),
    path('Edit_Subcontractor_schedule/<str:id>/<str:pid>', views.Edit_Subcontractor_schedule, name="Edit_Subcontractor_schedule"),
    path('Edit_Subcontractor_schedule_post/', views.Edit_Subcontractor_schedule_post, name="Edit_Subcontractor_schedule_post"),
    path('Delete_subschd/<str:id>/<str:pid>', views.Delete_subschd, name="Delete_subschd"),
    path('Edit_Subcontractor/<str:id>', views.Edit_Subcontractor, name="Edit_Subcontractor"),
    path('Edit_Subcontractor_post/', views.Edit_Subcontractor_post, name="Edit_Subcontractor_post"),
    path('Delete_subcontractor/<str:id>', views.Delete_subcontractor, name="Delete_subcontractor"),
    path('Edit_Uploaded_documents/<str:id>/<str:pid>', views.Edit_Uploaded_documents, name="Edit_Uploaded_documents"),
    path('Edit_Uploaded_documents_post/', views.Edit_Uploaded_documents_post, name="Edit_Uploaded_documents_post"),
    path('Delete_document/<str:id>/<str:pid>', views.Delete_document, name="Delete_document"),
    path('Edit_Uploaded_drawings/<str:id>/<str:pid>', views.Edit_Uploaded_drawings, name="Edit_Uploaded_drawings"),
    path('Edit_Uploaded_drawings_post/', views.Edit_Uploaded_drawings_post, name="Edit_Uploaded_drawings_post"),
    path('Delete_drawing/<str:id>/<str:pid>', views.Delete_drawing, name="Delete_drawing"),
    path('Edit_work_schedule/<str:id>/<str:pid>', views.Edit_work_schedule, name="Edit_work_schedule"),
    path('Edit_work_schedule_post/', views.Edit_work_schedule_post, name="Edit_work_schedule_post"),
    path('Delete_wshd/<str:id>/<str:pid>', views.Delete_wshd, name="Delete_wshd"),
    path('Edit_works/<str:id>/<str:pid>', views.Edit_works, name="Edit_works"),
    path('Edit_works_post/', views.Edit_works_post, name="Edit_works_post"),
    path('Delete_work/<str:id>/<str:pid>', views.Delete_work, name="Delete_work"),
    path('Delete_chatpm/<str:id>/<str:pid>', views.Delete_chatpm, name="Delete_chatpm"),
    path('chatspm/<str:id>/<str:msg>', views.chatspm, name="chatspm"),
    path('chatpm/<str:id>', views.chatpm, name="chatpm"),
    path('viewmsg_pm/<str:id>', views.viewmsg_pm, name="viewmsg_pm"),
    path('Issue_materials_to_site/<str:id>', views.Issue_materials_to_site, name="Issue_materials_to_site"),
    path('Issue_materials_to_site_post/', views.Issue_materials_to_site_post, name="Issue_materials_to_site_post"),
    path('Projec_allocation_to_purchaser/<str:id>', views.Projec_allocation_to_purchaser, name="Projec_allocation_to_purchaser"),
    path('Projec_allocation_to_purchaser_post/', views.Projec_allocation_to_purchaser_post, name="Projec_allocation_to_purchaser_post"),
    path('Upload_documents/<str:id>', views.Upload_documents, name="Upload_documents"),
    path('Upload_documents_post/', views.Upload_documents_post, name="Upload_documents_post"),
    path('Upload_drawings/<str:id>', views.Upload_drawings, name="Upload_drawings"),
    path('Upload_drawings_post/', views.Upload_drawings_post, name="Upload_drawings_post"),
    path('View_assigned_projects/', views.View_assigned_projects, name="View_assigned_projects"),
    path('search_aspp/', views.search_aspp, name="search_aspp"),
    path('View_completed_projectspm/', views.View_completed_projectspm, name="View_completed_projectspm"),
    path('search_aspcppm/', views.search_aspcppm, name="search_aspcppm"),
    path('View_budget/<str:id>', views.View_budget, name="View_budget"),
    path('search_bgtpm/', views.search_bgtpm, name="search_bgtpm"),
    path('View_Estimate/<str:id>', views.View_Estimate, name="View_Estimate"),
    path('search_est/', views.search_est, name="search_est"),
    path('View_issued_materials_to_site/<str:id>', views.View_issued_materials_to_site, name="View_issued_materials_to_site"),
    path('search_msd/', views.search_msd, name="search_msd"),
    path('View_materials_request/<str:id>', views.View_materials_request, name="View_materials_request"),
    path('search_mrt/', views.search_mrt, name="search_mrt"),
    path('View_materials_required/<str:id>', views.View_materials_required, name="View_materials_required"),
    path('search_msrd/', views.search_msrd, name="search_msrd"),
    path('View_materials_report/<str:id>', views.View_materials_report, name="View_materials_report"),
    path('search_msrt/', views.search_msrt, name="search_msrt"),
    path('View_material/', views.View_material, name="View_material"),
    path('search_mts/', views.search_mts, name="search_mts"),
    path('View_notification/', views.View_notification, name="View_notification"),
    path('search_ntfn/', views.search_ntfn, name="search_ntfn"),
    path('View_Ongoing_projects_pm/', views.View_Ongoing_projects_pm, name="View_Ongoing_projects_pm"),
    path('search_onp/', views.search_onp, name="search_onp"),
    path('View_projects_functionspm/<str:id>', views.View_projects_functionspm, name="View_projects_functionspm"),
    path('View_pending_materials_request/<str:id>', views.View_pending_materials_request, name="View_pending_materials_request"),
    path('search_pmrt/', views.search_pmrt, name="search_pmrt"),
    path('approve_rqt/<str:id>/<str:pid>', views.approve_rqt, name="approve_rqt"),
    path('reject_rqt/<str:id>/<str:pid>', views.reject_rqt, name="reject_rqt"),
    path('View_profile/', views.View_profile, name="View_profile"),
    path('View_Project_allocated_to_purchaser/<str:id>', views.View_Project_allocated_to_purchaser, name="View_Project_allocated_to_purchaser"),
    path('search_pcr/', views.search_pcr, name="search_pcr"),
    path('View_project_inspection/<str:id>', views.View_project_inspection, name="View_project_inspection"),
    path('search_insp/', views.search_insp, name="search_insp"),
    path('View_project_payment_entry/<str:id>', views.View_project_payment_entry, name="View_project_payment_entry"),
    path('search_pmnt/', views.search_pmnt, name="search_pmnt"),
    path('completed/', views.completed, name="completed"),
    path('View_project_status/<str:id>', views.View_project_status, name="View_project_status"),
    path('search_prstpm/', views.search_prstpm, name="search_prstpm"),
    path('View_Subcontractor_of_project/<str:id>', views.View_Subcontractor_of_project, name="View_Subcontractor_of_project"),
    path('search_sbcrpm/', views.search_sbcrpm, name="search_sbcrpm"),
    path('View_subcontractor_schedule/<str:id>', views.View_subcontractor_schedule, name="View_subcontractor_schedule"),
    path('View_subcontractor/', views.View_subcontractor, name="View_subcontractor"),
    path('search_sbr/', views.search_sbr, name="search_sbr"),
    path('View_uploaded_document/<str:id>', views.View_uploaded_document, name="View_uploaded_document"),
    path('search_udcms/', views.search_udcms, name="search_udcms"),
    path('View_uploaded_drawings/<str:id>', views.View_uploaded_drawings, name="View_uploaded_drawings"),
    path('search_udrws/', views.search_udrws, name="search_udrws"),
    path('View_work_schedules/<str:id>', views.View_work_schedules, name="View_work_schedules"),
    path('schedule_searchpm/', views.schedule_searchpm, name="schedule_searchpm"),
    path('View_work/<str:id>', views.View_work, name="View_work"),
    path('search_wrk/', views.search_wrk, name="search_wrk"),
    path('View_Worksite_photospm/<str:id>', views.View_Worksite_photospm, name="View_Worksite_photospm"),
    path('search_sppm/', views.search_sppm, name="search_sppm"),

    ########################################################  SUPERVISOR   ########################################################

    path('sphome/', views.sphome, name="sphome"),
    path('Add_daily_material_usage/<str:id>', views.Add_daily_material_usage, name="Add_daily_material_usage"),
    path('Add_daily_material_usage_post/', views.Add_daily_material_usage_post, name="Add_daily_material_usage_post"),
    path('Add_daily_workers_count/<str:id>', views.Add_daily_workers_count, name="Add_daily_workers_count"),
    path('Add_daily_workers_count_post/', views.Add_daily_workers_count_post, name="Add_daily_workers_count_post"),
    path('Change_password_sp/', views.Change_password_sp, name="Change_password_sp"),
    path('Change_password_sp_post/', views.Change_password_sp_post, name="Change_password_sp_post"),
    path('Edit_daily_material_usage/<str:id>/<str:pid>', views.Edit_daily_material_usage, name="Edit_daily_material_usage"),
    path('Edit_daily_material_usage_post/', views.Edit_daily_material_usage_post, name="Edit_daily_material_usage_post"),
    path('Delete_muse/<str:id>/<str:pid>', views.Delete_muse,name="Delete_muse"),
    path('Edit_daily_workers_count/<str:id>/<str:pid>', views.Edit_daily_workers_count, name="Edit_daily_workers_count"),
    path('Edit_daily_workers_count_post/', views.Edit_daily_workers_count_post, name="Edit_daily_workers_count_post"),
    path('Delete_dwc/<str:id>/<str:pid>', views.Delete_dwc, name="Delete_dwc"),
    path('Edit_material_request/<str:id>/<str:pid>', views.Edit_material_request, name="Edit_material_request"),
    path('Edit_material_request_post/', views.Edit_material_request_post, name="Edit_material_request_post"),
    path('Delete_mrt/<str:id>/<str:pid>', views.Delete_mrt, name="Delete_mrt"),
    path('Edit_Uploaded_site_photos/<str:id>/<str:pid>', views.Edit_Uploaded_site_photos, name="Edit_Uploaded_site_photos"),
    path('Edit_Uploaded_site_photos_post/', views.Edit_Uploaded_site_photos_post, name="Edit_Uploaded_site_photos_post"),
    path('Delete_usp/<str:id>/<str:pid>', views.Delete_usp, name="Delete_usp"),
    path('Delete_chatsp/<str:id>/<str:pid>', views.Delete_chatsp, name="Delete_chatsp"),
    path('chatssp/<str:id>/<str:msg>', views.chatssp, name="chatssp"),
    path('chatsp/<str:id>', views.chatsp, name="chatsp"),
    path('viewmsg_sp/<str:id>', views.viewmsg_sp, name="viewmsg_sp"),
    path('Send_material_request/<str:id>', views.Send_material_request, name="Send_material_request"),
    path('Send_material_request_post/', views.Send_material_request_post, name="Send_material_request_post"),
    path('Update_work_progress/<str:id>/<str:pid>/', views.Update_work_progress, name="Update_work_progress"),
    path('Update_work_progress_post/', views.Update_work_progress_post, name="Update_work_progress_post"),
    path('Upload_site_photos/<str:id>', views.Upload_site_photos, name="Upload_site_photos"),
    path('Upload_site_photos_post/', views.Upload_site_photos_post, name="Upload_site_photos_post"),
    path('View_assigned_projects_sp/', views.View_assigned_projects_sp, name="View_assigned_projects_sp"),
    path('search_asp/', views.search_asp, name="search_asp"),
    path('View_budget_sp/<str:id>', views.View_budget_sp, name="View_budget_sp"),
    path('search_bgtsp/', views.search_bgtsp, name="search_bgtsp"),
    path('View_completed_projects_sp/', views.View_completed_projects_sp, name="View_completed_projects_sp"),
    path('search_aspcp/', views.search_aspcp, name="search_aspcp"),
    path('View_daily_workers_count/<str:id>', views.View_daily_workers_count, name="View_daily_workers_count"),
    path('search_dwcr/', views.search_dwcr, name="search_dwcr"),
    path('View_daily_materials_usage/<str:id>', views.View_daily_materials_usage, name="View_daily_materials_usage"),
    path('search_dmur/', views.search_dmur, name="search_dmur"),
    path('View_drawings/<str:id>', views.View_drawings, name="View_drawings"),
    path('search_drws/', views.search_drws, name="search_drws"),
    path('View_documents/<str:id>', views.View_documents, name="View_documents"),
    path('search_dcms/', views.search_dcms, name="search_dcms"),
    path('View_estimate_sp/<str:id>', views.View_estimate_sp, name="View_estimate_sp"),
    path('search_estm/', views.search_estm, name="search_estm"),
    path('View_inspection_details/<str:id>', views.View_inspection_details, name="View_inspection_details"),
    path('search_inspection/', views.search_inspection, name="search_inspection"),
    path('View_material_request_report/<str:id>', views.View_material_request_report, name="View_material_request_report"),
    path('search_mrr/', views.search_mrr, name="search_mrr"),
    path('View_material_request/<str:id>', views.View_material_request, name="View_material_request"),
    path('search_mr/', views.search_mr, name="search_mr"),
    path('View_material_usage_report/<str:id>', views.View_material_usage_report, name="View_material_usage_report"),
    path('search_mur/', views.search_mur, name="search_mur"),
    path('View_material_issued_and_update_status/<str:id>', views.View_material_issued_and_update_status, name="View_material_issued_and_update_status"),
    path('Update_issue_status/<str:id>', views.Update_issue_status,name="Update_issue_status"),
    path('search_misd/', views.search_misd, name="search_misd"),
    path('View_material_required/<str:id>', views.View_material_required,name="View_material_required"),
    path('search_mrd/', views.search_mrd, name="search_mrd"),
    path('View_Ongoing_project_sp/', views.View_Ongoing_project_sp, name="View_Ongoing_project_sp"),
    path('search_ongp/', views.search_ongp, name="search_ongp"),
    path('View_projects_functionsp/<str:id>', views.View_projects_functionsp, name="View_projects_functionsp"),
    path('View_profile_sp/', views.View_profile_sp, name="View_profile_sp"),
    path('View_project_payment/<str:id>', views.View_project_payment, name="View_project_payment"),
    path('search_payment/', views.search_payment, name="search_payment"),
    path('View_schedule/<str:id>', views.View_schedule, name="View_schedule"),
    path('schedule_search/', views.schedule_search, name="schedule_search"),
    path('search_subsh/', views.search_subsh, name="search_subsh"),
    path('View_subcontractor_schedule_sp/<str:id>', views.View_subcontractor_schedule_sp, name="View_subcontractor_schedule_sp"),
    path('View_Subcontractor/<str:id>', views.View_Subcontractor, name="View_Subcontractor"),
    path('search_subc/', views.search_subc, name="search_subc"),
    path('View_Uploaded_site_photos/<str:id>', views.View_Uploaded_site_photos, name="View_Uploaded_site_photos"),
    path('search_usp/', views.search_usp, name="search_usp"),
    path('View_work_status_report/<str:id>', views.View_work_status_report, name="View_work_status_report"),
    path('View_work_progress/<str:id>/<str:pid>/', views.View_work_progress, name="View_work_progress"),
    path('Delete_wps/<str:id>/<str:wid>/<str:pid>', views.Delete_wps, name="Delete_wps"),
    path('View_work_sp/<str:id>', views.View_work_sp, name="View_work_sp"),
    path('search_work/', views.search_work, name="search_work"),
    path('View_worker_count_report/<str:id>', views.View_worker_count_report, name="View_worker_count_report"),
    path('search_wcr/', views.search_wcr, name="search_wcr"),

    #######################################################     ACCOUNTANT   ###############################################################
    path('achome/', views.achome, name="achome"),
    path('Add_account_sub/', views.Add_account_sub, name="Add_account_sub"),
    path('Add_account_sub_post/', views.Add_account_sub_post, name="Add_account_sub_post"),
    path('Add_accounthead/', views.Add_accounthead, name="Add_accounthead"),
    path('Add_accounthead_post/', views.Add_accounthead_post, name="Add_accounthead_post"),
    path('Change_password_ac/', views.Change_password_ac, name="Change_password_ac"),
    path('Change_password_ac_post/', views.Change_password_ac_post, name="Change_password_ac_post"),
    path('Edit_accounthead/<str:id>', views.Edit_accounthead, name="Edit_accounthead"),
    path('Edit_accounthead_post/', views.Edit_accounthead_post, name="Edit_accounthead_post"),
    path('Delete_Accounthead/<str:id>', views.Delete_Accounthead, name="Delete_Accounthead"),
    path('Edit_account_sub/<str:id>', views.Edit_account_sub, name="Edit_account_sub"),
    path('Edit_account_sub_post/', views.Edit_account_sub_post, name="Edit_account_sub_post"),
    path('Delete_Accountsub/<str:id>', views.Delete_Accountsub, name="Delete_Accountsub"),
    path('Edit_Transaction_entry/<str:id>', views.Edit_Transaction_entry, name="Edit_Transaction_entry"),
    path('Edit_Transaction_entry_post/', views.Edit_Transaction_entry_post, name="Edit_Transaction_entry_post"),
    path('Delete_Transaction/<str:id>', views.Delete_Transaction, name="Delete_Transaction"),
    path('Delete_chatac/<str:id>/<str:pid>', views.Delete_chatac, name="Delete_chatac"),
    path('chatsac/<str:id>/<str:msg>', views.chatsac, name="chatsac"),
    path('chatac/<str:id>', views.chatac, name="chatac"),
    path('viewmsg_ac/<str:id>', views.viewmsg_ac, name="viewmsg_ac"),
    path('Edit_Project_payment_entry/<str:id>/<str:pid>', views.Edit_Project_payment_entry, name="Edit_Project_payment_entry"),
    path('Edit_Project_payment_entry_post/', views.Edit_Project_payment_entry_post, name="Edit_Project_payment_entry_post"),
    path('Delete_Payment/<str:id>/<str:pid>', views.Delete_Payment, name="Delete_Payment"),
    path('Project_payment_entry/<str:id>', views.Project_payment_entry, name="Project_payment_entry"),
    path('Project_payment_entry_post/', views.Project_payment_entry_post, name="Project_payment_entry_post"),
    path('Transaction_entry/', views.Transaction_entry, name="Transaction_entry"),
    path('Transaction_entry_post/', views.Transaction_entry_post, name="Transaction_entry_post"),
    path('View_account_head/', views.View_account_head, name="View_account_head"),
    path('search_achd/', views.search_achd, name="search_achd"),
    path('View_accountsub/', views.View_accountsub, name="View_accountsub"),
    path('search_acntsub/', views.search_acntsub, name="search_acntsub"),
    path('View_profile_ac/', views.View_profile_ac, name="View_profile_ac"),
    path('View_project_payment_entry_ac/<str:id>', views.View_project_payment_entry_ac, name="View_project_payment_entry_ac"),
    path('search_pymtey/', views.search_pymtey, name="search_pymtey"),
    path('View_Project_statusac/<str:id>', views.View_Project_statusac, name="View_Project_statusac"),
    path('search_prstac/', views.search_prstac, name="search_prstac"),
    path('View_all_projects/', views.View_all_projects, name="View_all_projects"),
    path('search_allprjtsac/', views.search_allprjtsac, name="search_allprjtsac"),
    path('View_projects/', views.View_projects, name="View_projects"),
    path('search_prjtsac/', views.search_prjtsac, name="search_prjtsac"),
    path('View_projects_functionsac/<str:id>', views.View_projects_functionsac, name="View_projects_functionsac"),
    path('View_Completed_projects/', views.View_Completed_projects, name="View_Completed_projects"),
    path('search_prjtscdac/', views.search_prjtscdac, name="search_prjtscdac"),
    path('View_transaction_entry/', views.View_transaction_entry, name="View_transaction_entry"),
    path('search_tnct/', views.search_tnct, name="search_tnct"),

   ################################################PURCHASER###################################################

    path('pchome/', views.pchome, name="pchome"),
    path('view_assigned_projectspc/', views.view_assigned_projectspc, name="view_assigned_projectspc"),
    path('search_asppc/', views.search_asppc, name="search_asppc"),
    path('view_completed_projectspc/', views.view_completed_projectspc, name="view_completed_projectspc"),
    path('search_aspcdpc/', views.search_aspcdpc, name="search_aspcdpc"),
    path('view_ongoing_projectpc/', views.view_ongoing_projectpc, name="view_ongoing_projectpc"),
    path('search_ongppc/', views.search_ongppc, name="search_ongppc"),
    path('View_projects_functionspr/<str:id>', views.View_projects_functionspr, name="View_projects_functionspr"),
    path('view_profilepc/', views.view_profilepc, name="view_profilepc"),
    path('Change_password_pc/', views.Change_password_pc, name="Change_password_pc"),
    path('View_material_requiredpc/<str:id>', views.View_material_requiredpc, name="View_material_requiredpc"),
    path('search_mrdpc/', views.search_mrdpc, name="search_mrdpc"),
    path('View_materials_requestpc/<str:id>', views.View_materials_requestpc, name="View_materials_requestpc"),
    path('search_mrtpc/', views.search_mrtpc, name="search_mrtpc"),
    path('View_delivered_materials/<str:id>', views.View_delivered_materials, name="View_delivered_materials"),
    path('search_deld/', views.search_deld, name="search_deld"),
    path('View_material_issuedpc/<str:id>', views.View_material_issuedpc, name="View_material_issuedpc"),
    path('search_misdpc/', views.search_misdpc, name="search_misdpc"),
    path('Update_issue_statuspc/<str:id>', views.Update_issue_statuspc, name="Update_issue_statuspc"),
    path('View_work_progresspc/<str:id>', views.View_work_progresspc, name="View_work_progresspc"),
    path('search_prstapc/', views.search_prstapc, name="search_prstapc"),
    path('deliver_materials/<str:id>', views.deliver_materials, name="deliver_materials"),
    path('deliver_materials_post/', views.deliver_materials_post, name="deliver_materials_post"),
    path('Edit_delivered_materials/<str:id>', views.Edit_delivered_materials, name="Edit_delivered_materials"),
    path('Edit_delivered_materials_post/', views.Edit_delivered_materials_post, name="Edit_delivered_materials_post"),
    path('Delete_drdm/<str:id>/<str:pid>', views.Delete_drdm, name="Delete_drdm"),
    path('Delete_chatpc/<str:id>/<str:pid>', views.Delete_chatpc, name="Delete_chatpc"),
    path('chatspc/<str:id>/<str:msg>', views.chatspc, name="chatspc"),
    path('chatpc/<str:id>', views.chatpc, name="chatpc"),
    path('viewmsg_pc/<str:id>', views.viewmsg_pc, name="viewmsg_pc"),
    path('View_notification_ajax', views.View_notification_ajax, name="View_notification_ajax"),

]

