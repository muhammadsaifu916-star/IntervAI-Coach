from django.urls import path
from . import views

urlpatterns = [
    # Owner-facing
    path('me/',                          views.my_profile,            name='profile_me'),
    path('me/publish/',                  views.publish_profile,       name='profile_publish'),
    path('me/unpublish/',                views.unpublish_profile,     name='profile_unpublish'),

    # Employer-facing
    path('public/',                      views.public_profiles_list,  name='public_profiles_list'),
    path('public/<int:user_id>/',        views.public_profile_detail, name='public_profile_detail'),
]
