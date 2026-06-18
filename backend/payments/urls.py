from django.urls import path
from . import views

urlpatterns = [
    path('packages/',                     views.list_packages,   name='packages_list'),
    path('purchase/',                     views.create_purchase, name='purchase_create'),
    path('purchases/',                    views.my_purchases,    name='purchases_list'),
    path('unlock/<int:candidate_id>/',    views.unlock_profile,  name='profile_unlock'),
    path('unlocks/',                      views.my_unlocks,      name='unlocks_list'),
]
