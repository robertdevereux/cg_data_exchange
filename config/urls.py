"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.1/topics/http/urls/
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
from django.urls import include, path
from django.views.generic import RedirectView
from django.views.static import serve
from django.conf import settings
import os

# Local static directory that holds our GDS assets.
_GDS_STATIC = os.path.join(settings.BASE_DIR, 'core', 'static')

# The GOV.UK Frontend CDN CSS hardcodes these absolute paths.
# Serve our local copies at exactly those URLs so no CSS override is needed.
_gds_assets = [
    'assets/images/govuk-crest.svg',
    'assets/fonts/bold-affa96571d-v2.woff',
    'assets/fonts/bold-b542beb274-v2.woff2',
    'assets/fonts/light-94a07e06a1-v2.woff2',
    'assets/fonts/light-f591b13f7d-v2.woff',
]

urlpatterns = [
    path('admin/', admin.site.urls),
    path('accounts/', include('django.contrib.auth.urls')),
    path('', include('core.urls', namespace='core')),
    path('demo/', include('dept_demo.urls', namespace='dept_demo')),
] + [
    path(asset, serve, {
        'path': 'govuk-' + asset,   # maps to core/static/govuk-assets/...
        'document_root': _GDS_STATIC,
    })
    for asset in _gds_assets
] + [
    path('', RedirectView.as_view(url='/demo/', permanent=False)),
]
