from django import forms
from django.forms.models import BaseInlineFormSet
from .models import *
from assays.models import AssayChipSetup
from mps.forms import SignOffMixin

# These are all of the tracking fields
tracking = ('created_by', 'created_on', 'modified_on', 'modified_by', 'signed_off_by', 'signed_off_date')


class MicrodeviceForm(SignOffMixin, forms.ModelForm):
    """Form for Microdevices"""
    class Meta(object):
        model = Microdevice
        exclude = tracking

        widgets = {
            'device_name': forms.Textarea(attrs={'rows': 1}),
            'description': forms.Textarea(attrs={'rows': 3}),
        }


class OrganModelForm(SignOffMixin, forms.ModelForm):
    """Form for Organ Models"""
    class Meta(object):
        model = OrganModel
        exclude = tracking

        widgets = {
            'model_name': forms.Textarea(attrs={'rows': 1}),
            'description': forms.Textarea(attrs={'rows': 3}),
        }


class OrganModelProtocolInlineFormset(BaseInlineFormSet):
    """Form for Organ Model Protocols (as part of an inline)"""
    class Meta(object):
        model = OrganModelProtocol
        exclude = ('',)

    def clean(self):
        forms_data = [f for f in self.forms if f.cleaned_data]

        for form in forms_data:
            data = form.cleaned_data
            protocol_id = data.get('id', '')
            delete_checked = data.get('DELETE', False)

            # Make sure that no protocol in use is checked for deletion
            if protocol_id and delete_checked:
                if AssayChipSetup.objects.filter(organ_model_protocol=protocol_id):
                    raise forms.ValidationError('You cannot remove protocols that are referenced by a chip setup.')