from django.urls import path
from . import views

urlpatterns = [
    path('start/',  views.start_quiz,  name='quiz_start'),
    path('submit/', views.submit_quiz, name='quiz_submit'),
    path('latest/', views.latest_quiz, name='quiz_latest'),
]