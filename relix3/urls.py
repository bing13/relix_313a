"""relix3 URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/3.0/topics/http/urls/
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
from django.urls import include,path

urlpatterns = [
    # mfa seems to need to be the first, or at least before /admin
    path('admin/multifactor/', include('multifactor.urls')),
    path('admin/', admin.site.urls),    
    path("__debug__/", include("debug_toolbar.urls")),
    path('relix/',include('relix.urls')),
    path(r'ckeditor/', include('ckeditor_uploader.urls')),

]

#more lib/python3.8/site-packages/multifactor/urls.py 


# from django.conf.urls import url
# from django.contrib.auth.decorators import login_required
# from django.views.decorators.cache import never_cache

# from ckeditor_uploader.views import upload, browse

# urlpatterns += [
#     # url patterns for ckedit are in PROJECT relix3/relix3/urls.py,
#     #path('ckeditor/', include('ckeditor_uploader.urls')),
#     # adding instead to my local urls.py, so I can use logon_required decorator, not staff_member
#     # https://django-ckeditor.readthedocs.io/en/latest/#required-for-using-widget-with-file-upload
#     #    don't want to use the staff member decorator, so these two go here
#     #    Found them in ~/django3/lib/python3.8/site-packages/ckeditor_uploader/urls.py
#     url(r'^upload/', login_required(upload), name='ckeditor_upload'),
#     url(r'^browse/', login_required(never_cache(browse)), name='ckeditor_browse'),
#     #url(r'^ckeditor/', include('ckeditor_uploader.urls')),
    
#     ]
