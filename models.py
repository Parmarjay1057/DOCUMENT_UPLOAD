
from django.db import models
from django.utils import timezone
from datetime import timedelta
import uuid

# Create your models here.
class User(models.Model):
    name = models.CharField(max_length=50)
    email = models.EmailField()
    pwd = models.CharField(max_length=100)
    gender = models.CharField(max_length=20)
    is_superadmin = models.BooleanField(default=False)  # <-- add this field
    last_login = models.DateTimeField(null=True, blank=True)
    def __str__(self):
        return self.name

class File_Upload(models.Model):
    user = models.ForeignKey(User, models.CASCADE, related_name='sent_files', null=True, blank=True)
    receiver = models.ForeignKey(User, models.CASCADE, related_name='received_files', null=True, blank=True)
    title = models.CharField(max_length=50)
    description = models.TextField()
    file_field = models.FileField(upload_to="uploads/")
    shared_at = models.DateTimeField(default=timezone.now)
    document_list = models.ForeignKey('DocumentList', null=True, blank=True, on_delete=models.SET_NULL)
    guest_uploader_name = models.CharField(max_length=100, null=True, blank=True)  # <--- Add this field

    def __str__(self):
        return self.title


class FileRequest(models.Model):
    requester = models.ForeignKey(User, on_delete=models.CASCADE, related_name='sent_requests')
    receiver = models.ForeignKey(User, on_delete=models.CASCADE, related_name='received_requests')
    message = models.TextField()
    requested_at = models.DateTimeField(default=timezone.now)

    seen = models.BooleanField(default=False)  # 🔴 Add this line

    def __str__(self):
        return f"Request from {self.requester.name} to {self.receiver.name}"

class DocumentList(models.Model):
    """A predefined list of documents required for a specific purpose."""
    name = models.CharField(max_length=100)  # e.g., "New Employee Onboarding"
    description = models.TextField(blank=True)
    created_by = models.ForeignKey('User', on_delete=models.CASCADE, related_name='document_lists')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

class DocumentListItem(models.Model):
    """An individual document name/item part of a DocumentList."""
    document_list = models.ForeignKey(DocumentList, on_delete=models.CASCADE, related_name='items')
    title = models.CharField(max_length=100)   # e.g., "Resume", "Identity Proof"
    description = models.TextField(blank=True) # optional detail or instructions

    def __str__(self):
        return f"{self.title} ({self.document_list.name})" 

class RequestedFile(models.Model):
    file_request = models.ForeignKey(FileRequest, on_delete=models.CASCADE, related_name='requested_files')
    document_list_item = models.ForeignKey(DocumentListItem, on_delete=models.CASCADE, null=True, blank=True)
    file = models.ForeignKey(File_Upload, on_delete=models.CASCADE, null=True, blank=True)  # make nullable to allow pending uploads
    accepted = models.BooleanField(null=True, blank=True)  # Null = pending, True = accepted, False = rejected

    def __str__(self):
        return f"{self.file.title if self.file else 'No File'} in request {self.file_request.id}"

class TemporaryUploadLink(models.Model):
    file_request = models.ForeignKey(FileRequest, on_delete=models.CASCADE)
    token = models.CharField(max_length=64, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()

    def is_valid(self):
        return timezone.now() < self.expires_at

    def __str__(self):
        return f"Temp Link for {self.file_request}"
    


class GuestUploadLink(models.Model):
    token = models.UUIDField(default=uuid.uuid4, unique=True)
    phone = models.CharField(max_length=20)
    message = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_in_minutes = models.IntegerField(default=10)
    requester = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='guest_upload_links'
    )
    
    document_list_name = models.CharField(max_length=255, blank=True, null=True)  # New field

    def is_expired(self):
        return timezone.now() > self.created_at + timedelta(minutes=self.expires_in_minutes)

    def upload_url(self):
        return f"/upload-temp/{self.token}/"
        
     