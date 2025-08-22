# from django.contrib import admin
# from .models import User, File_Upload
# from .models import RequiredDocument

# # Register your models here.
# admin.site.register(User)
# admin.site.register(File_Upload)
# admin.site.register(RequiredDocument)


from django.contrib import admin
from .models import User, File_Upload


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ('name', 'email', 'gender', 'is_superadmin', 'last_login')
    search_fields = ('name', 'email')
    list_filter = ('gender', 'is_superadmin')

@admin.register(File_Upload)
class FileUploadAdmin(admin.ModelAdmin):
    list_display = ('title', 'user', 'receiver', 'shared_at')
    search_fields = ('title', 'description', 'user__name', 'receiver__name')
    list_filter = ('shared_at',)
