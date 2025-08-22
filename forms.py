from django import forms
from .models import User, DocumentList, DocumentListItem

class PredefinedDocumentRequestForm(forms.Form):
    receiver = forms.ModelChoiceField(
        queryset=User.objects.all(), 
        label="Request To"
    )
    document_list = forms.ModelChoiceField(
        queryset=DocumentList.objects.all(),
        label="Document List"
    )
    documents = forms.ModelMultipleChoiceField(
        queryset=DocumentListItem.objects.none(),
        widget=forms.CheckboxSelectMultiple,
        label="Select Documents to Request",
    )

    def __init__(self, *args, **kwargs):
        document_list_id = kwargs.pop('document_list_id', None)
        super().__init__(*args, **kwargs)
        if document_list_id:
            self.fields['document_list'].initial = document_list_id
            self.fields['documents'].queryset = DocumentListItem.objects.filter(document_list_id=document_list_id)
        else:
            self.fields['documents'].queryset = DocumentListItem.objects.none()
