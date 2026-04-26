from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('start/', views.start_job, name='start_job'),
    path('progress/<uuid:job_id>/', views.progress, name='progress'),
    path('api/job/<uuid:job_id>/status/', views.job_status_api, name='job_status_api'),
    path('results/<uuid:job_id>/', views.results, name='results'),
    path('error/<uuid:job_id>/', views.error_view, name='error_view'),
    path('download/<uuid:job_id>/', views.download_csv, name='download_csv'),
]
