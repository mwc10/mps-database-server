from django.conf.urls import patterns
from django.contrib import admin
from django.contrib import messages
from django import forms
from django.shortcuts import render_to_response
from django.template import RequestContext
from django.http import HttpResponseRedirect
from bioservices import ChEMBL as ChEMBLdb

from compounds.resource import CompoundResource
from mps.base.admin import LockableAdmin
from compounds.models import *
from compounds.forms import *


class CompoundTargetInline(admin.TabularInline):
    formset = CompoundTargetInlineFormset
    model = CompoundTarget

    fields = (
        ('name', 'uniprot_id', 'type', 'organism', 'pharmacological_action', 'action')
    )
    extra = 0


class CompoundSummaryInline(admin.TabularInline):
    # Assays for ChipReadout
    formset = CompoundSummaryInlineFormset
    model = CompoundSummary
    verbose_name = 'Compound Summary'
    verbose_plural_name = 'Compound Summaries'

    fields = (
        ('compound', 'summary_type', 'summary', 'source')
    )
    extra = 0

    # class Media(object):
    #     css = {"all": ("css/hide_admin_original.css",)}


class CompoundPropertyInline(admin.TabularInline):
    # Assays for ChipReadout
    formset = CompoundPropertyInlineFormset
    model = CompoundProperty
    verbose_name = 'Compound Properties'
    verbose_plural_name = 'Compound Properties'

    fields = (
        (
            ('compound', 'property_type', 'value', 'source')
        ),
    )
    extra = 0

    # class Media(object):
    #     css = {"all": ("css/hide_admin_original.css",)}


class CompoundAdminForm(forms.ModelForm):

    class Meta(object):
        model = Compound
        widgets = {
            'clearance': forms.Textarea(attrs={'cols': 75, 'rows': 10}),
            'absorption': forms.Textarea(attrs={'cols': 75, 'rows': 10}),
            'pk_metabolism': forms.Textarea(attrs={'cols': 75, 'rows': 10}),
            'preclinical': forms.Textarea(attrs={'cols': 75, 'rows': 10}),
            'clinical': forms.Textarea(attrs={'cols': 75, 'rows': 10}),
            'post_marketing': forms.Textarea(attrs={'cols': 75, 'rows': 10}),
        }
        exclude = []


class CompoundAdmin(LockableAdmin):
    form = CompoundAdminForm
    resource_class = CompoundResource

    class Media(object):
        js = ('compounds/customize_admin.js',)

    class AddMultiForm(forms.Form):

        chemblids = forms.CharField(required=True, label="ChEMBL IDs",
                                    widget=forms.Textarea(),
                                    help_text="<br>ChEMBL IDs separated by a "
                                              "space or a new line.")
    # Compound summary and compound properties are deprecated
    #inlines = [CompoundSummaryInline, CompoundPropertyInline, CompoundTargetInline]
    inlines = [CompoundTargetInline]

    save_on_top = True
    list_per_page = 300
    list_display = ('name', 'chembl_link', 'known_drug',
                    'molecular_formula', 'tags', 'mps', 'epa', 'last_update', 'locked')
    search_fields = ['=name', 'synonyms', '=chemblid', 'tags']
    readonly_fields = ('last_update', 'created_by', 'created_on',
                       'modified_by', 'modified_on', 'image_display')
    actions = ['update_fields']

    def image_display(self, obj):
        if obj.chemblid:
            url = (
                u'https://www.ebi.ac.uk/chembldb/compound/'
                'displayimage/' + obj.chemblid)
            print '<img src="%s">' % \
                url
            return '<img src="%s">' % \
                url
        return ''

    image_display.allow_tags = True
    image_display.short_description = 'Structure'

    fieldsets = (
        (None, {
            'fields': (('name', 'image_display'),
                       ('chemblid', 'pubchemid', 'drugbank_id', 'inchikey'),
                       ('mps', 'epa'),
                       'last_update',)
        }),
        ('Molecular Identifiers', {
            'fields': ('smiles', 'synonyms')
        }),
        ('Molecular Properties', {
            'fields': ('molecular_formula', 'molecular_weight',
                       'rotatable_bonds',
                       'acidic_pka', 'basic_pka',
                       'logp', 'logd', 'alogp',)
        }),
        ('Drug(-like) Properties', {
            'fields': ('known_drug', 'medchem_alerts', 'ro3_passes',
                       'ro5_violations', 'species', 'drug_class', 'protein_binding',
                       'half_life', 'bioavailability'
            )
        }),
        ('Summaries', {
            'fields': ('absorption', 'clearance', 'pk_metabolism', 'preclinical', 'clinical', 'post_marketing'
            )
        }),
        ('Change Tracking', {
            'fields': (
                'locked',
                ('created_by', 'created_on'),
                ('modified_by', 'modified_on'),
                ('signed_off_by', 'signed_off_date'),
            )
        }
        ),
    )

    def get_urls(self):

        return patterns('',
                        (r'^add_multi/$',
                         self.admin_site.admin_view(self.add_compounds))
        ) + super(CompoundAdmin, self).get_urls()

    def add_compounds(self, request):

        if '_add' in request.POST:
            form = self.AddMultiForm(request.POST)
            if form.is_valid():
                chemblids = form.cleaned_data['chemblids']
                counter = skipped = invalid = notfound = 0
                chemblids = chemblids.split()
                for chemblid in chemblids:
                    if not chemblid.startswith('CHEMBL'):
                        invalid += 1
                        continue
                    if Compound.objects.filter(chemblid=chemblid):
                        skipped += 1
                        continue
                    try:
                        data = ChEMBLdb().get_compounds_by_chemblId(
                            str(chemblid)
                        )
                    except Exception:
                        notfound += 1
                    else:
                        if data:
                            counter += 1
                            data['locked'] = True
                            Compound.objects.create(**data)

                if counter:
                    self.message_user(request,
                                      "Successfully added {} compound{}."
                                      .format(counter,
                                              '' if counter == 1 else 's'))
                if skipped:
                    self.message_user(request, "Skipped {} compound{} that "
                                               "{} already in the database."
                                      .format(skipped,
                                              '' if skipped == 1 else 's',
                                              'is' if skipped == 1 else 'are'),
                                      level=messages.WARNING)
                if invalid:
                    self.message_user(request, "Skipped {} invalid "
                                               "identifier{}."
                                      .format(invalid,
                                              '' if invalid == 1 else 's'),
                                      level=messages.WARNING)
                if notfound:
                    self.message_user(request,
                                      "Could not find {} identifier{} in "
                                      "ChEMBL database."
                                      .format(notfound,
                                              '' if notfound == 1 else 's'),
                                      level=messages.WARNING)

                return HttpResponseRedirect(request.get_full_path())
        else:
            form = self.AddMultiForm()

        return render_to_response('compounds/add_multi.html', {
            'title': 'Add multiple compounds',
            'opts': self.model._meta,
            'form': form,
            # 'root_path': self.admin_site.root_path,
        }, context_instance=RequestContext(request))


admin.site.register(Compound, CompoundAdmin)


class SummaryTypeAdmin(LockableAdmin):
    save_on_top = True

    search_fields = ['name', 'description',]
    list_filter = ['name',]

    list_display = (
        'name',
        'description'
    )

    readonly_fields = ('created_by', 'created_on',
                       'modified_by', 'modified_on',)

    fieldsets = (
       (
           "Summary Type Data", {
               'fields': (
                   'name',
                   'description',
               )
           }
       ),
       ('Change Tracking', {
           'fields': (
               'locked',
               ('created_by', 'created_on'),
               ('modified_by', 'modified_on'),
               ('signed_off_by', 'signed_off_date'),
           )
       }
       ),
    )


admin.site.register(SummaryType, SummaryTypeAdmin)


class PropertyTypeAdmin(LockableAdmin):
    save_on_top = True

    search_fields = ['name', 'description',]
    list_filter = ['name',]

    list_display = (
        'name',
        'description'
    )

    readonly_fields = ('created_by', 'created_on',
                       'modified_by', 'modified_on',)

    fieldsets = (
       (
           "Property Data", {
               'fields': (
                   'name',
                   'description',
               )
           }
       ),
       ('Change Tracking', {
           'fields': (
               'locked',
               ('created_by', 'created_on'),
               ('modified_by', 'modified_on'),
               ('signed_off_by', 'signed_off_date'),
           )
       }
       ),
    )


admin.site.register(PropertyType, PropertyTypeAdmin)
