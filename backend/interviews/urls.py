from django.urls import path
from . import views

urlpatterns = [
    path('start/',       views.start_interview,       name='interview_start'),
    path('monitoring/',  views.submit_monitoring,       name='interview_monitoring'),
    path('transcribe/',  views.transcribe_answer,       name='interview_transcribe'),
    path('submit/',      views.submit_interview,        name='interview_submit'),
    path('latest/',      views.latest_interview,        name='interview_latest'),
]
