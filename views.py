TEMP_UPLOADS = {}

SUPER_ADMIN_EMAIL = "superadmin@gmail.com"

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.utils import timezone
from urllib.parse import quote
import secrets
from datetime import timedelta
from .models import User, File_Upload, FileRequest, RequestedFile, GuestUploadLink, DocumentList, DocumentListItem
from django.contrib import messages
from django.http import HttpResponseForbidden, HttpResponseBadRequest
from django.db.models import Q
from django.utils.dateparse import parse_datetime
from datetime import datetime, timezone as dt_timezone
from urllib.parse import quote
from django.utils.crypto import get_random_string
from .models import TemporaryUploadLink
import os
import uuid
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from .forms import PredefinedDocumentRequestForm
from django.db.models import Prefetch


def login(request):
    if 'user' not in request.session:
        if request.method == 'POST':
            email = request.POST['email']
            pwd = request.POST['pwd']

            # Use filter to find matching user (you might want to hash passwords for security)
            user_qs = User.objects.filter(email=email, pwd=pwd)
            if user_qs.exists():
                user = user_qs.first()
                request.session["user"] = user.email

                # Store previous last_login, or default to 1970-01-01 UTC if None
                prev_last_login = user.last_login or datetime(1970, 1, 1, tzinfo=dt_timezone)
                request.session['prev_last_login'] = prev_last_login.isoformat()

                # Update last_login to current time
                user.last_login = timezone.now()
                user.save()

                if user.email == SUPER_ADMIN_EMAIL:
                    return redirect('superadmin_file_shares')
                else:
                    return redirect('index')
            else:
                messages.warning(request, "Wrong user or details.")
        return render(request, 'login.html')
    else:
        # If already logged in, redirect to appropriate page
        email = request.session['user']
        if email == SUPER_ADMIN_EMAIL:
            return redirect('superadmin_file_shares')
        else:
            return redirect('index')


def index(request):
    if 'user' not in request.session:
        return redirect('login')

    email = request.session['user']

    if email == SUPER_ADMIN_EMAIL:
        return redirect('superadmin_file_shares')

    current_user = User.objects.get(email=email)

    # Retrieve previous login time
    prev_last_login_iso = request.session.get('prev_last_login')
    if prev_last_login_iso:
        prev_last_login = parse_datetime(prev_last_login_iso)
        if prev_last_login is None:
            prev_last_login = datetime(1970, 1, 1, tzinfo=dt_timezone.utc)
    else:
        prev_last_login = datetime(1970, 1, 1, tzinfo=dt_timezone.utc)

    # 🔔 New files after last login
    new_files = File_Upload.objects.filter(
        receiver=current_user,
        shared_at__gt=prev_last_login
    ).order_by('-shared_at')

    # 🔔 New: Get file requests
    file_requests = FileRequest.objects.filter(receiver=current_user).order_by('-requested_at')[:5]
    request_count = FileRequest.objects.filter(receiver=current_user).count()

    query = request.GET.get('q', '').strip()
    section = request.GET.get('section', 'shared')

    shared_files = File_Upload.objects.filter(user=current_user).order_by('-shared_at')
    received_files = File_Upload.objects.filter(receiver=current_user).order_by('-shared_at')

    if query:
        if section == 'shared':
            shared_files = shared_files.filter(
                Q(title__icontains=query) | Q(description__icontains=query)
            )
            received_files = File_Upload.objects.none()
        elif section == 'received':
            received_files = received_files.filter(
                Q(title__icontains=query) |
                Q(description__icontains=query) |
                Q(user__name__icontains=query)
            )
            shared_files = File_Upload.objects.none()

    return render(request, 'index.html', {
        'shared_files': shared_files,
        'received_files': received_files,
        'query': query,
        'active_section': section,
        'new_files_count': new_files.count(),
        'new_files': new_files,
        'file_requests': file_requests,      # ✅ pass requests to template
        'request_count': request_count       # ✅ pass request count
    })


def logout(request):
    request.session.flush()  # clears entire session and regenerates session key
    return redirect('login')


def signup(request):
    if request.method == 'POST':
        name = request.POST['name']
        email = request.POST['email']
        pwd = request.POST['pwd']
        gender = request.POST['gender']
        if not User.objects.filter(email=email).exists():
            create_user = User.objects.create(name=name, email=email, pwd=pwd, gender=gender)
            create_user.save()
            messages.success(request, "Your account is created successfully!")
            return redirect('login')
        else:
            messages.warning(request, "Email is already registered!")

    return render(request, 'signup.html')


def settings(request):
    if 'user' in request.session:
        user_obj = User.objects.get(email=request.session['user'])
        user_files = File_Upload.objects.filter(user=user_obj)

        img_list = []
        audio_list = []
        videos_list = []
        pdfs_list = []

        for file in user_files:
            ext = str(file.file_field).split('.')[-1].lower()
            if ext == 'mp3':
                audio_list.append(file)
            elif ext in ['mp4', 'mkv']:
                videos_list.append(file)
            elif ext in ['jpg', 'jpeg', 'png']:
                img_list.append(file)
            elif ext == 'pdf':
                pdfs_list.append(file)

        data = {
            'user_files': user_files,
            'videos': len(videos_list),
            'audios': len(audio_list),
            'images': len(img_list),
            'pdf': len(pdfs_list),
            'img_list': img_list,
            'audio_list': audio_list,
            'videos_list': videos_list,
            'pdfs_list': pdfs_list
        }

        return render(request, 'settings.html', data)
    else:
        return redirect('login')  # ✅ Fix: handle case when user is not logged in

def file_upload(request):
    if 'user' not in request.session:
        return redirect('login')

    current_user = User.objects.get(email=request.session['user'])
    all_users = User.objects.exclude(email=SUPER_ADMIN_EMAIL)
    document_lists = DocumentList.objects.all()

    if request.method == 'POST':
        # -------- Handle file upload form --------
        if 'upload_file' in request.POST:
            uploaded_files = []

            files = request.FILES.getlist('file_to_upload')
            if not files:
                messages.error(request, "No files selected for upload.")
                return redirect('file_upload')

            receiver_id = request.POST.get('receiver_id')
            receiver = None
            if receiver_id:
                try:
                    receiver = User.objects.get(id=receiver_id)
                except User.DoesNotExist:
                    messages.error(request, "Selected receiver not found.")
                    return redirect('file_upload')

            title = request.POST.get('title', None)
            description = request.POST.get('description', '')

            for f in files:
                file_title = title if title else f.name
                file_instance = File_Upload.objects.create(
                    title=file_title,
                    description=description,
                    file_field=f,
                    user=current_user,
                    receiver=receiver,
                    shared_at=timezone.now(),
                )
                uploaded_files.append(file_instance)

            messages.success(request, f"{len(uploaded_files)} file(s) uploaded successfully!")
            return redirect('file_upload')

        # -------- Handle file request form --------
        elif 'request_files' in request.POST:
            receiver_id = request.POST.get('request_receiver_id', '').strip()
            guest_phone = request.POST.get('guest_phone', '').strip()
            request_message = request.POST.get('request_message', '').strip()
            document_list_id = request.POST.get('document_list')
            selected_documents = request.POST.getlist('documents')

            # Validation
            if not receiver_id and not guest_phone:
                messages.error(request, "Please select a registered user or enter a guest phone number.")
                return redirect('file_upload')

            if receiver_id and guest_phone:
                messages.error(request, "Please choose either registered user OR guest phone, not both.")
                return redirect('file_upload')

            # ------------------------------
            # Case 1: Guest / Non-user request
            # ------------------------------
            if guest_phone:
                document_list_name = None
                if document_list_id:
                    try:
                        document_list = DocumentList.objects.get(id=document_list_id)
                        document_list_name = document_list.name
                    except DocumentList.DoesNotExist:
                        document_list_name = None

                link = GuestUploadLink.objects.create(
                    phone=guest_phone,
                    message=request_message,
                    requester=current_user,
                    document_list_name=document_list_name
                )
                upload_url = request.build_absolute_uri(f"/upload-temp/{link.token}/")

                message_text = f"{request_message}\nPlease upload your document here:\n{upload_url}"
                wa_url = f"https://wa.me/{guest_phone}?text={quote(message_text)}"

                # Save to session so template shows WA + Upload link
                request.session['wa_url'] = wa_url
                request.session['upload_link'] = upload_url
                request.session['selected_document_list_name'] = document_list_name

                messages.success(request, "File request sent and temporary upload link generated.")
                return redirect('file_upload')

            # ------------------------------
            # Case 2: Registered User request
            # ------------------------------
            if receiver_id:
                try:
                    receiver = User.objects.get(id=receiver_id)
                except User.DoesNotExist:
                    messages.error(request, "Selected user not found.")
                    return redirect('file_upload')

                if receiver.email == SUPER_ADMIN_EMAIL:
                    messages.error(request, "You cannot request files from the super admin.")
                    return redirect('file_upload')

                file_request = FileRequest.objects.create(
                    requester=current_user,
                    receiver=receiver,
                    message=request_message
                )

                if document_list_id:
                    if selected_documents:
                        # Use only the checked documents
                        valid_docs = DocumentListItem.objects.filter(
                            id__in=selected_documents,
                            document_list_id=document_list_id
                        )
                    else:
                        # If no items were manually selected, add ALL items from the chosen list
                        valid_docs = DocumentListItem.objects.filter(
                            document_list_id=document_list_id
                        )

                    for doc_item in valid_docs:
                        RequestedFile.objects.create(
                            file_request=file_request,
                            document_list_item=doc_item
                        )

                # ✅ IMPORTANT: No upload_link in session for registered users
                messages.success(request, "Request is sent successfully.")
                return redirect('file_upload')

        else:
            messages.error(request, "Invalid form submission.")
            return redirect('file_upload')

    # -------- GET request --------
    wa_url = request.session.pop('wa_url', None)
    upload_link = request.session.pop('upload_link', None)
    selected_document_list_name = request.session.pop('selected_document_list_name', None)

    return render(request, 'file_upload.html', {
        'all_users': all_users,
        'document_lists': document_lists,
        'wa_url': wa_url,
        'upload_link': upload_link,
        'selected_document_list_name': selected_document_list_name,
    })

def temporary_upload_view(request, token):
    try:
        link = GuestUploadLink.objects.get(token=token)
    except GuestUploadLink.DoesNotExist:
        return HttpResponseBadRequest("Invalid or expired upload link.")

    if hasattr(link, 'is_expired') and link.is_expired():
        return HttpResponseBadRequest("The upload link has expired.")

    guest_name = ''
    document_list_items = []
    if link.document_list_name:
        try:
            doc_list = DocumentList.objects.get(name=link.document_list_name)
            document_list_items = list(doc_list.items.all())
        except DocumentList.DoesNotExist:
            document_list_items = []

    file_requests = FileRequest.objects.filter(receiver=link.requester)
    file_request = file_requests.first() if file_requests.exists() else None

    # Mark uploaded status BEFORE POST processing so 'uploaded' exists
    for item in document_list_items:
        item.uploaded = RequestedFile.objects.filter(
            document_list_item=item,
            file_request__receiver=link.requester,
            file__isnull=False
        ).exists()

    if request.method == "POST":
        guest_name = request.POST.get('guest_name', '').strip()
        error = None

        if not guest_name:
            messages.error(request, "Please enter your name.")
        else:
            any_upload_error = False
            for item in document_list_items:
                # Now it is safe to check item.uploaded
                if item.uploaded:
                    continue

                file_key = f'file_{item.id}'
                uploaded_file = request.FILES.get(file_key)

                if not uploaded_file:
                    any_upload_error = True
                    continue

                # You can add validation here (file size, type, etc.)

                # Save the uploaded file and link to requester and document item
                file_upload = File_Upload.objects.create(
                    title=f"Guest Upload: {item.title}",
                    description=link.message or "",
                    file_field=uploaded_file,
                    user=None,  # guest uploader
                    receiver=link.requester,  # who requested the upload
                    guest_uploader_name=guest_name,
                    shared_at=timezone.now(),
                )

                if file_request:
                    RequestedFile.objects.create(
                        file_request=file_request,
                        document_list_item=item,
                        file=file_upload,
                        accepted=None,
                    )

            if any_upload_error:
                messages.error(request, "Some documents were not uploaded. Please select files for all required documents.")
            else:
                messages.success(request, "All documents uploaded successfully.")

        # After POST upload, refresh uploaded status again:
        for item in document_list_items:
            item.uploaded = RequestedFile.objects.filter(
                document_list_item=item,
                file_request__receiver=link.requester,
                file__isnull=False
            ).exists()

    all_uploaded = all(getattr(item, 'uploaded', False) for item in document_list_items) if document_list_items else False

    return render(request, "guest_upload.html", {
        "document_list_name": link.document_list_name,
        "document_list_items": document_list_items,
        "guest_name": guest_name,
        "all_uploaded": all_uploaded,
    })

# New AJAX view to return documents for a selected DocumentList
def get_list_items(request):
    list_id = request.GET.get('document_list_id')
    items = []
    if list_id:
        items = DocumentListItem.objects.filter(document_list_id=list_id).values('id', 'title')
    return JsonResponse({'items': list(items)})

def delete_file(request, id):
    if 'user' not in request.session:
        return redirect('login')

    referer_url = request.META.get('HTTP_REFERER', 'index')
    user_email = request.session['user']

    try:
        file_obj = File_Upload.objects.get(id=id)

        # Safely get file owner's email if available
        file_user_email = file_obj.user.email if file_obj.user else None

        # Allow deletion only if:
        # - Current user is the owner of the file, OR
        # - The current user is the superadmin
        if user_email != SUPER_ADMIN_EMAIL and file_user_email != user_email:
            messages.error(request, "You are not allowed to delete this file.", extra_tags=f"file-{id}")
            return redirect(referer_url)

        file_obj.delete()
        messages.success(request, "File deleted successfully.", extra_tags=f"file-{id}")

    except File_Upload.DoesNotExist:
        messages.warning(request, "File not found.", extra_tags=f"file-{id}")

    return redirect(referer_url)

def home(request):
    return render(request, 'index.html') 

def message_list(request):
    messages = File_Upload.objects.all().order_by('-sent_at')
    return render(request, 'index.html', {'messages': messages})

def superadmin_file_shares(request):
    if 'user' not in request.session:
        return redirect('login')

    current_user_email = request.session['user']

    if current_user_email != SUPER_ADMIN_EMAIL:
        return HttpResponseForbidden("You are not authorized to view this page.")

    query = request.GET.get('q', '').strip()

    shared_files = File_Upload.objects.select_related('user', 'receiver').all().order_by('-shared_at')

    if query:
        shared_files = shared_files.filter(
            Q(title__icontains=query) |
            Q(description__icontains=query) |
            Q(user__name__icontains=query) |
            Q(user__email__icontains=query) |
            Q(receiver__name__icontains=query) |
            Q(receiver__email__icontains=query) |
            Q(guest_uploader_name__icontains=query)
        )

    return render(request, 'superadmin_file_shares.html', {
        'shared_files': shared_files
    })

def file_detail_view(request, id):
    if 'user' not in request.session:
        return redirect('login')

    user_email = request.session['user']
    if user_email != SUPER_ADMIN_EMAIL:
        return HttpResponseForbidden("You are not authorized to view this page.")

    try:
        file_obj = File_Upload.objects.get(id=id)
    except File_Upload.DoesNotExist:
        messages.warning(request, "File not found.", extra_tags=f"file-{id}")
        return redirect('superadmin_file_shares')

    # Optional permission checks can be added here if needed

    if not file_obj.file_field or not os.path.exists(file_obj.file_field.path):
        messages.warning(request, "This file is not available.", extra_tags=f"file-{id}")
        return redirect('superadmin_file_shares')

    return render(request, 'file_detail.html', {
        'file': file_obj,
    })

@csrf_exempt
def mark_requests_seen(request):
    if request.method == "POST":
        user_id = request.session.get("user_id")
        if user_id:
            FileRequest.objects.filter(receiver_id=user_id, seen=False).update(seen=True)
            return JsonResponse({"status": "success"})
        else:
            return JsonResponse({"status": "unauthorized"}, status=403)
    return JsonResponse({"status": "invalid method"}, status=405)


def file_request_list(request):
    if 'user' not in request.session:
        return redirect('login')

    email = request.session['user']

    try:
        user = User.objects.get(email=email)
    except User.DoesNotExist:
        return redirect('login')

    search_query = request.GET.get('q', '').strip()  # Get search query from GET params

    def add_display_flags(requests):
        """Add helper flags for template display."""
        for r in requests:
            r.show_message = bool(r.message)
            r.show_docs = not r.show_message  # Only show docs if no message
        return requests

    if email == SUPER_ADMIN_EMAIL:
        all_requests = FileRequest.objects.select_related('requester', 'receiver').prefetch_related(
            Prefetch('requested_files', queryset=RequestedFile.objects.select_related('document_list_item'))
        )

        if search_query:
            all_requests = all_requests.filter(
                Q(requester__name__icontains=search_query) |
                Q(requester__email__icontains=search_query) |
                Q(receiver__name__icontains=search_query) |
                Q(receiver__email__icontains=search_query)
            )

        all_requests = all_requests.order_by('-requested_at')
        all_requests = add_display_flags(all_requests)

        return render(request, 'superadmin_file_requests.html', {
            'all_requests': all_requests,
            'search_query': search_query,
        })

    else:
        received_requests = FileRequest.objects.filter(receiver=user).prefetch_related(
            Prefetch('requested_files', queryset=RequestedFile.objects.select_related('document_list_item'))
        )

        sent_requests = FileRequest.objects.filter(requester=user).prefetch_related(
            Prefetch('requested_files', queryset=RequestedFile.objects.select_related('document_list_item'))
        )

        if search_query:
            received_requests = received_requests.filter(
                Q(requester__name__icontains=search_query) |
                Q(requester__email__icontains=search_query) |
                Q(receiver__name__icontains=search_query) |
                Q(receiver__email__icontains=search_query)
            )
            sent_requests = sent_requests.filter(
                Q(requester__name__icontains=search_query) |
                Q(requester__email__icontains=search_query) |
                Q(receiver__name__icontains=search_query) |
                Q(receiver__email__icontains=search_query)
            )

        received_requests = received_requests.order_by('-requested_at')
        sent_requests = sent_requests.order_by('-requested_at')

        received_requests = add_display_flags(received_requests)
        sent_requests = add_display_flags(sent_requests)

        return render(request, 'file_requests.html', {
            'received_requests': received_requests,
            'sent_requests': sent_requests,
            'search_query': search_query,
        })


def delete_file_request(request, id):
    if 'user' not in request.session:
        return redirect('login')

    file_request = get_object_or_404(FileRequest, id=id)
    current_user_email = request.session['user']

    if current_user_email != SUPER_ADMIN_EMAIL and file_request.requester.email != current_user_email:
        messages.error(request, "You are not authorized to delete this request.")
        return redirect('file_requests')

    if request.method == 'POST':
        file_request.delete()
        messages.success(request, "The request has been removed.", extra_tags="file_requests")
        return redirect('file_requests')

    return redirect('file_requests')

def pre_defined_lists_view(request):
    edit_list_id = None  # track which list is currently in edit mode

    # Get current logged-in user for created_by field & permission checks
    current_user_email = request.session.get('user')
    if not current_user_email:
        messages.error(request, "You must be logged in to manage predefined lists.")
        return redirect('login')

    try:
        current_user = User.objects.get(email=current_user_email)
    except User.DoesNotExist:
        messages.error(request, "User not found.")
        return redirect('login')

    # Handle search query from GET parameters
    search_query = request.GET.get('search', '').strip()
    if search_query:
        document_lists = DocumentList.objects.filter(
            Q(name__icontains=search_query) | Q(description__icontains=search_query)
        )
    else:
        document_lists = DocumentList.objects.all()

    if request.method == 'POST':
        # Create new document list
        if 'create_list' in request.POST:
            name = request.POST.get('name', '').strip()
            description = request.POST.get('description', '').strip()

            if not name:
                messages.error(request, "List name cannot be empty.")
            else:
                doc_list = DocumentList.objects.create(
                    name=name,
                    description=description,
                    created_by=current_user
                )
                for line in description.splitlines():
                    clean_line = line.strip()
                    if clean_line:
                        DocumentListItem.objects.create(
                            document_list=doc_list,
                            title=clean_line
                        )
                messages.success(request, "New predefined document list created with documents.")
                return redirect('predefined_lists')

        # Start editing a list — show edit form for that list
        elif 'start_edit' in request.POST:
            edit_list_id = request.POST.get('edit_list')

        # Save edits to an existing list
        elif 'edit_list' in request.POST:
            list_id = request.POST.get('edit_list')
            doc_list = DocumentList.objects.filter(id=list_id).first()
            if not doc_list:
                messages.error(request, "Document list not found.")
            else:
                name = request.POST.get('name', '').strip()
                description = request.POST.get('description', '').strip()
                if not name:
                    messages.error(request, "Name cannot be empty.")
                    edit_list_id = list_id  # stay in edit mode
                else:
                    doc_list.name = name
                    doc_list.description = description
                    doc_list.save()
                    messages.success(request, "List updated successfully.")
                    return redirect('predefined_lists')

    return render(request, 'predefined_lists.html', {
        'document_lists': document_lists,
        'edit_list_id': edit_list_id,
        'search_query': search_query,  # pass search query to template for input retention
    })


def delete_predefined_list(request, list_id):
    if 'user' not in request.session:
        messages.error(request, "You must be logged in to delete.")
        return redirect('predefined_lists')

    current_user_email = request.session['user']
    doc_list = get_object_or_404(DocumentList, id=list_id)

    # Permission: only superadmin or creator can delete
    if not (current_user_email == SUPER_ADMIN_EMAIL or doc_list.created_by.email == current_user_email):
        messages.error(request, "You are not authorized to delete this list.")
        return redirect('predefined_lists')

    if request.method == 'POST':
        doc_list.delete()
        messages.success(request, "Pre-defined document list deleted.")
        return redirect('predefined_lists')

    return redirect('predefined_lists')

def view_file(request, id):
    """
    Intercept file access. If missing or no permission, show flash message instead of 404.
    Supports ?download=1 to force a download.
    """
    if 'user' not in request.session:
        return redirect('login')

    user_email = request.session['user']
    redirect_view = 'superadmin_file_shares' if user_email == SUPER_ADMIN_EMAIL else 'index'

    try:
        file_obj = File_Upload.objects.get(id=id)
    except File_Upload.DoesNotExist:
        messages.warning(request, "File not found.", extra_tags=f"file-{id}")
        return redirect(redirect_view)

    # Permission check
    if user_email != SUPER_ADMIN_EMAIL and not (
        (file_obj.user and file_obj.user.email == user_email) or
        (file_obj.receiver and file_obj.receiver.email == user_email)
    ):
        messages.error(request, "You are not authorized to view this file.", extra_tags=f"file-{id}")
        return redirect(redirect_view)

    # Physical file existence check
    if not file_obj.file_field or not os.path.exists(file_obj.file_field.path):
        messages.warning(request, "This file is not available.", extra_tags=f"file-{id}")
        return redirect(redirect_view)

    # ✅ If file exists
    if request.GET.get("download") == "1":
        from django.http import FileResponse
        return FileResponse(
            open(file_obj.file_field.path, 'rb'),
            as_attachment=True,
            filename=os.path.basename(file_obj.file_field.name)
        )
    else:
        return redirect(file_obj.file_field.url)
