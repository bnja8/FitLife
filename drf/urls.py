"""
URL configuration for drf project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.conf import settings
from django.conf.urls.static import static
from django.urls import path
from api import views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', views.home_page, name='home'),
    path('sedes/', views.gym_locations_page, name='gym-locations'),
    path('panel/', views.dashboard_page, name='dashboard'),
    path('iniciar-sesion/', views.auth_page, name='auth'),
    path('api/plans', views.plans, name='api-plans'),
    path('api/plans/<int:plan_id>', views.plan_detail, name='api-plan-detail'),
    path('api/memberships', views.create_membership, name='api-memberships'),
    path('api/memberships/purchase', views.purchase_membership, name='api-membership-purchase'),
    path('api/memberships/trial', views.redeem_free_trial, name='api-membership-trial'),
    path('api/payments/webpay/return', views.webpay_return, name='api-webpay-return'),
    path('api/auth/register', views.register, name='api-register'),
    path('api/auth/login', views.login, name='api-login'),
    path('api/auth/logout', views.logout, name='api-logout'),
    path('api/auth/me', views.me, name='api-me'),
    path('api/auth/credential', views.issue_credential, name='api-credential'),
    path('api/auth/credential/qr', views.credential_qr, name='api-credential-qr'),
    path('api/dashboard', views.dashboard, name='api-dashboard'),
    path('api/public/sessions', views.public_sessions, name='api-public-sessions'),
    path('api/public/installations', views.public_installations, name='api-public-installations'),
    path('api/sessions', views.sessions, name='api-sessions'),
    path('api/sessions/<int:session_id>', views.update_session, name='api-session-update'),
    path('api/sessions/<int:session_id>/observations', views.update_session_observations, name='api-session-observations'),
    path('api/sessions/<int:session_id>/status', views.update_session_status, name='api-session-status'),
    path('api/sessions/<int:session_id>/reserve', views.reserve_session, name='api-reserve'),
    path('api/reservations/<int:reservation_id>/cancel', views.cancel_reservation, name='api-cancel-reservation'),
    path('api/sessions/<int:session_id>/attendance', views.record_attendance, name='api-attendance'),
    path('api/machines', views.machines, name='api-machines'),
    path('api/access-points', views.access_points, name='api-access-points'),
    path('api/access-points/<int:access_point_id>', views.access_point_detail, name='api-access-point-detail'),
    path('api/installations', views.installations, name='api-installations'),
    path('api/installations/<int:installation_id>', views.installation_detail, name='api-installation-detail'),
    path('api/installations/<int:installation_id>/instructors', views.installation_instructors, name='api-installation-instructors'),
    path('api/rooms', views.rooms, name='api-rooms'),
    path('api/machines/<int:machine_id>', views.machine_detail, name='api-machine'),
    path('api/users/<str:rut>', views.user_detail, name='api-user'),
    path('api/users/<str:rut>/roles', views.user_roles, name='api-user-roles'),
    path('api/users', views.create_staff_user, name='api-users'),
    path('api/followups', views.followups, name='api-followups'),
    path('api/professional/workspace', views.professional_workspace, name='api-professional-workspace'),
    path('api/access/validate', views.validate_access, name='api-access'),
    path('api/admin/data', views.admin_data, name='api-admin-data'),
    path('api/admin/data/<str:entity>', views.admin_data, name='api-admin-data-entity'),
    path('api/admin/data/<str:entity>/<str:record_id>', views.admin_data, name='api-admin-data-record'),
]

handler404 = 'api.middleware.page_not_found'

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
