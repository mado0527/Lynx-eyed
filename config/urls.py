"""
URL configuration for config project.

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
from django.urls import path
from crowd_app.views import home, information_page, device_management, weekly_graph, prediction_graph
from django.views.generic import RedirectView
from crowd_app.management import dashboard, ManagementLoginView, ManagementLogoutView, DataManagementLoginView, DataManagementLogoutView

urlpatterns = [
    path('', home, name='home'),
    path('prediction-graph/', prediction_graph, name='prediction'),
    path('weekly-graph/', weekly_graph, name='weekly'),
    path('live/', information_page, {'page': 'live'}, name='live'),
    path('help/', information_page, {'page': 'help'}, name='help'),
    path('device-management/', device_management, name='devices'),
    path('management/login/', ManagementLoginView.as_view(), name='management_login'),
    path('management/logout/', ManagementLogoutView.as_view(), name='management_logout'),
    path('management/', dashboard, name='management'),
    path('login/', RedirectView.as_view(pattern_name='management_login', permanent=False, query_string=True)),
    path('admin/login/', DataManagementLoginView.as_view()),
    path('admin/logout/', DataManagementLogoutView.as_view()),
    path('admin/', admin.site.urls),
]
