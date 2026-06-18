from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from rest_framework_simplejwt.views import TokenRefreshView
from users.views import CustomTokenObtainPairView


ADMIN_APP_ORDER = {
    "users": 1,
    "resumes": 2,
    "quizzes": 3,
    "interviews": 4,
    "profiles": 5,
    "payments": 6,
}


original_get_app_list = admin.site.get_app_list


def custom_get_app_list(request, app_label=None):
    app_list = original_get_app_list(request, app_label)

    app_list.sort(
        key=lambda app: ADMIN_APP_ORDER.get(app["app_label"], 999)
    )

    return app_list


admin.site.get_app_list = custom_get_app_list


urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/users/',      include('users.urls')),
    path('api/resumes/',    include('resumes.urls')),
    path('api/quizzes/',    include('quizzes.urls')),
    path('api/interviews/', include('interviews.urls')),
    path('api/profiles/',   include('profiles.urls')),
    path('api/payments/',   include('payments.urls')),

    path('api/token/', CustomTokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('api/token/refresh/', TokenRefreshView.as_view(),    name='token_refresh'),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)