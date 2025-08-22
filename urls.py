from django.urls import path
from . import views
from django.contrib import admin
from django.conf import settings
from django.conf.urls.static import static

admin.site.site_header = "Document Upload"
admin.site.site_title = "Document Upload Portal"
admin.site.index_title = "Welcome to Document Upload Portal"

urlpatterns = [
    path('', views.index, name="index"),
    path('login/', views.login, name="login"),
    path('logout/', views.logout, name="logout"),
    path('signup/', views.signup, name="signup"),
    path('settings/', views.settings, name="settings"),
    path('file_upload/', views.file_upload, name="file_upload"),
    path('file-requests/', views.file_request_list, name='file_requests'),
    path('delete/<str:id>/', views.delete_file, name="delete_file"),
    path('home/', views.home, name='home'),
    path('superadmin/file-shares/', views.superadmin_file_shares, name="superadmin_file_shares"),
    path('requests/', views.index, name="request_inbox"),
    path('mark-requests-seen/', views.mark_requests_seen, name='mark_requests_seen'),
    path('upload-temp/<str:token>/', views.temporary_upload_view, name='temporary_upload'),
    path('delete-request/<int:id>/', views.delete_file_request, name='delete_file_request'),
    path('predefined-lists/', views.pre_defined_lists_view, name='predefined_lists'),
    path('predefined-lists/delete/<int:list_id>/', views.delete_predefined_list, name='delete_predefined_list'),
    path('get_list_items/', views.get_list_items, name='get_list_items'),
    path('view/<int:id>/', views.view_file, name='view_file'),
    path('superadmin/file/<int:id>/', views.file_detail_view, name='file_detail_view'),

]

# ✅ Serve uploaded media files during development
if settings.DEBUG:
   urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

    

