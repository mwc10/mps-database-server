# coding=utf-8

from django.views.generic import ListView, CreateView, DetailView, UpdateView, DeleteView
from assays.models import *
from cellsamples.models import CellSample
from assays.admin import *
from assays.forms import *
from django import forms

from django.forms.models import inlineformset_factory
from django.shortcuts import redirect, get_object_or_404, render_to_response
from django.contrib.auth.models import Group
#from django.core.exceptions import PermissionDenied
from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator

from mps.templatetags.custom_filters import *
from django.db.models import Q

from mps.mixins import *

import ujson as json

# TODO Refactor imports
# TODO TODO REFACTOR WHITTLING TO BE IN FORM AS OPPOSED TO VIEW

# NOTE THAT YOU NEED TO MODIFY INLINES HERE, NOT IN FORMS

# Class-based views for indexes
class UserIndex(OneGroupRequiredMixin, ListView):
    context_object_name = 'user_index'
    template_name = 'assays/index.html'

    def get_context_data(self, request, **kwargs):
        self.object_list = AssayRun.objects.filter(created_by=request.user).prefetch_related('created_by', 'group')
        return super(UserIndex, self).get_context_data(**kwargs)

    def get(self, request, **kwargs):
        context = self.get_context_data(request, **kwargs)
        self.queryset = self.object_list
        context['title'] = request.user.username + "'s Studies"
        return self.render_to_response(context)


class GroupIndex(OneGroupRequiredMixin, ListView):
    context_object_name = 'group_index'
    template_name = 'assays/index.html'

    def get_context_data(self, request, **kwargs):
        groups = request.user.groups.values_list('pk', flat=True)
        groups = Group.objects.filter(pk__in=groups)
        self.object_list = AssayRun.objects.filter(group__in=groups).prefetch_related('created_by', 'group')
        return super(GroupIndex, self).get_context_data(**kwargs)

    def get(self, request, **kwargs):
        context = self.get_context_data(request, **kwargs)
        self.queryset = self.object_list
        context['title'] = 'Group Study Index'
        return self.render_to_response(context)


class StudyIndex(ObjectGroupRequiredMixin, DetailView):
    model = AssayRun
    context_object_name = 'study_index'
    template_name = 'assays/study_index.html'

    # TODO OPTIMIZE DATABASE HITS
    def get(self, request, **kwargs):
        self.object = self.get_object()

        context = self.get_context_data()

        context['setups'] = AssayChipSetup.objects.filter(assay_run_id=self.object).prefetch_related('device',
                                                                                                       'compound',
                                                                                                       'created_by')
        readouts = AssayChipReadout.objects.filter(chip_setup=context['setups']).prefetch_related(
            'created_by').select_related('chip_setup__compound',
                                                                   'chip_setup__unit')

        related_assays = AssayChipReadoutAssay.objects.filter(readout_id__in=readouts).prefetch_related('readout_id','assay_id')
        related_assays_map = {}

        for assay in related_assays:
            # start appending to a list keyed by the readout ID for all related images
            related_assays_map.setdefault(assay.readout_id.id, []).append(assay)

        for readout in readouts:
            # set an attribute on the readout that is the list created above
            readout.related_assays = related_assays_map.get(readout.id)

        context['readouts'] = readouts

        context['results'] = AssayChipResult.objects.prefetch_related('result_function', 'result_type',
                                                    'test_unit').select_related('assay_result__chip_readout__chip_setup',
                                                                                'assay_result__chip_readout__chip_setup__unit',
                                                                                'assay_name__assay_id',
                                                                                'assay_result__created_by').filter(assay_result__chip_readout=context['readouts'])

        context['number_of_results'] = AssayChipTestResult.objects.filter(chip_readout=context['readouts']).count()

        # PLATES

        context['plate_setups'] = AssayPlateSetup.objects.filter(assay_run_id=self.object).prefetch_related('assay_layout',
                                                                                                       'created_by')
        readouts = AssayPlateReadout.objects.filter(setup=context['plate_setups']).prefetch_related('setup', 'created_by')

        related_assays = AssayPlateReadoutAssay.objects.filter(readout_id__in=readouts).prefetch_related('readout_id','assay_id')
        related_assays_map = {}

        for assay in related_assays:
            # start appending to a list keyed by the readout ID for all related images
            related_assays_map.setdefault(assay.readout_id.id, []).append(assay)

        for readout in readouts:
            # set an attribute on the readout that is the list created above
            readout.related_assays = related_assays_map.get(readout.id)

        context['plate_readouts'] = readouts

        context['plate_results'] = AssayPlateResult.objects.prefetch_related('result_function', 'result_type',
                                                    'test_unit', 'assay_result').select_related('assay_result__readout__setup',
                                                                                'assay_result__readout__setup__unit',
                                                                                'assay_name__assay_id',
                                                                                'assay_result__created_by').filter(assay_result__readout=context['plate_readouts'])

        context['number_of_plate_results'] = AssayPlateTestResult.objects.filter(readout=context['plate_readouts']).count()

        return self.render_to_response(context)


# Class-based views for studies
class AssayRunList(LoginRequiredMixin, ListView):
    model = AssayRun

    def get_queryset(self):
        return AssayRun.objects.filter(restricted=False).prefetch_related('created_by', 'group') | AssayRun.objects.filter(
            group__in=self.request.user.groups.all()).prefetch_related('created_by', 'group')


class AssayRunAdd(OneGroupRequiredMixin, CreateView):
    template_name = 'assays/assayrun_add.html'
    form_class = AssayRunForm

    def get_form(self,form_class):
        # Get group selection possibilities
        groups = self.request.user.groups.filter(
            ~Q(name__contains="Add ") & ~Q(name__contains="Change ") & ~Q(name__contains="Delete "))

        # If POST
        if self.request.method == 'POST':
            return form_class(groups, self.request.POST)
        # If GET
        else:
            return form_class(groups)

    # Test form validity
    def form_valid(self, form):
        if form.is_valid():
            self.object = form.save()
            self.object.modified_by = self.object.created_by = self.request.user
            # Save Study
            self.object.save()
            return redirect(
                self.object.get_absolute_url())
        else:
            return self.render_to_response(self.get_context_data(form=form))


class AssayRunDetail(DetailView):
    model = AssayRun

    # Study detail view does not use DetailRedirectMixin because of differing URL
    @method_decorator(login_required)
    def dispatch(self, *args, **kwargs):
        self.object = self.get_object()
        # If user CAN edit the item, redirect to the respective edit page
        if has_group(self.request.user, self.object.group):
            return redirect('/assays/' + str(self.object.id))
        elif self.object.restricted:
            return PermissionDenied(self.request,'You must be a member of the group ' + str(self.object.group))
        return super(AssayRunDetail, self).dispatch(*args, **kwargs)

    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        context = self.get_context_data(object=self.object)
        context['setups'] = AssayChipSetup.objects.filter(assay_run_id=self.object).prefetch_related('assay_run_id',
                                                                                                     'device',
                                                                                                     'compound',
                                                                                                     'unit',
                                                                                                     'created_by')
        readouts = AssayChipReadout.objects.filter(chip_setup=context['setups']).prefetch_related(
            'chip_setup', 'created_by').select_related('chip_setup__compound',
                                                                   'chip_setup__unit')

        related_assays = AssayChipReadoutAssay.objects.filter(readout_id__in=readouts).prefetch_related('readout_id','assay_id')
        related_assays_map = {}

        for assay in related_assays:
            # start appending to a list keyed by the readout ID for all related images
            related_assays_map.setdefault(assay.readout_id.id, []).append(assay)

        for readout in readouts:
            # set an attribute on the readout that is the list created above
            readout.related_assays = related_assays_map.get(readout.id)

        context['readouts'] = readouts

        context['results'] = AssayChipResult.objects.prefetch_related('assay_name', 'assay_result', 'result_function', 'result_type',
                                                    'test_unit').select_related('assay_result__chip_readout__chip_setup',
                                                                                'assay_result__chip_readout__chip_setup__unit',
                                                                                'assay_name__assay_id',
                                                                                'assay_result__created_by').filter(assay_result__chip_readout=context['readouts'])

        return self.render_to_response(context)


class AssayRunUpdate(ObjectGroupRequiredMixin, UpdateView):
    model = AssayRun
    template_name = 'assays/assayrun_add.html'
    form_class = AssayRunForm

    def get_form(self,form_class):
        # Get group selection possibilities
        groups = self.request.user.groups.filter(
            ~Q(name__contains="Add ") & ~Q(name__contains="Change ") & ~Q(name__contains="Delete "))

        # If POST
        if self.request.method == 'POST':
            return form_class(groups, self.request.POST, instance=self.get_object())
        # If GET
        else:
            return form_class(groups, instance=self.get_object())

    def get(self, request, *args, **kwargs):
        form = self.get_form(self.form_class)

        return self.render_to_response(
            self.get_context_data(form=form,
                                  update=True))

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()

        form = self.get_form(self.form_class)

        if form.is_valid():
            self.object = form.save()
            self.object.modified_by = self.request.user
            # Save study
            self.object.save()
            return redirect(self.object.get_absolute_url())
        else:
            return self.render_to_response(
            self.get_context_data(form=form,
                                  update=True))


class AssayRunDelete(CreatorRequiredMixin, DeleteView):
    model = AssayRun
    template_name = 'assays/assayrun_delete.html'
    success_url = '/assays/user_index/'

    def get(self, request, *args, **kwargs):
        self.object = self.get_object()

        context = self.get_context_data()

        context['setups'] = AssayChipSetup.objects.filter(assay_run_id=self.object.id).prefetch_related('compound','unit')
        context['readouts'] = AssayChipReadout.objects.filter(chip_setup=context['setups'])
        context['results'] = AssayChipTestResult.objects.filter(chip_readout=context['readouts'])

        return self.render_to_response(context)


# Class based view for chip setups
class AssayChipSetupList(LoginRequiredMixin, ListView):
    model = AssayChipSetup

    def get_queryset(self):
        return AssayChipSetup.objects.filter(assay_run_id__restricted=False).prefetch_related('assay_run_id', 'device',
                                                                                              'compound', 'unit',
                                                                                              'created_by', 'group') | AssayChipSetup.objects.filter(
            assay_run_id__group__in=self.request.user.groups.all()).prefetch_related('assay_run_id', 'device',
                                                                                     'compound', 'unit', 'created_by', 'group')


AssayChipCellsFormset = inlineformset_factory(AssayChipSetup, AssayChipCells, formset=AssayChipCellsInlineFormset,
                                              extra=1,
                                              widgets={
                                              'cellsample_density': forms.NumberInput(attrs={'style': 'width:100px;', }),
                                              'cell_passage': forms.TextInput(attrs={'size': 5}), })


# TODO REFACTOR THE WAY CLONING IS HANDLED !!!IMPRORTANT
class AssayChipSetupAdd(CreateView):
    model = AssayChipSetup
    template_name = 'assays/assaychipsetup_add.html'
    # May want to define form with initial here
    form_class = AssayChipSetupForm

    # Due to the ability to clone, AssayChipSetupAdd is an exception to normal StudyGroupRequired permission
    @method_decorator(login_required)
    def dispatch(self, *args, **kwargs):
        study = get_object_or_404(AssayRun, pk=self.kwargs['study_id'])
        if not has_group(self.request.user, study.group):
            return PermissionDenied(self.request,'You must be a member of the group ' + str(study.group))

        if self.request.GET.get('clone',''):
            clone = get_object_or_404(AssayChipSetup, pk=self.request.GET.get('clone',''))
            if not has_group(self.request.user, clone.assay_run_id.group):
                return PermissionDenied(self.request,'You must be a member of the group ' + str(clone.assay_run_id.group) + ' to clone this setup')

        return super(AssayChipSetupAdd, self).dispatch(*args, **kwargs)

    def get_form(self, form_class):
        if self.request.method == 'POST':
            return form_class(self.request.POST)
        elif self.request.GET.get('clone',''):
            pk = int(self.request.GET.get('clone',''))
            clone = get_object_or_404(AssayChipSetup, pk=pk)
            return form_class(instance=clone)
        else:
            return form_class()

    def get_context_data(self, **kwargs):
        groups = self.request.user.groups.values_list('id', flat=True)
        cellsamples = CellSample.objects.filter(group__in=groups).order_by('-receipt_date').prefetch_related(
            'cell_type',
            'supplier',
        ).select_related('cell_type__cell_subtype')
        context = super(AssayChipSetupAdd, self).get_context_data(**kwargs)

        if self.request.POST:
            context['formset'] = AssayChipCellsFormset(self.request.POST)

        elif self.request.GET.get('clone',''):
            pk = int(self.request.GET.get('clone',''))
            clone = get_object_or_404(AssayChipSetup, pk=pk)
            context['formset'] = AssayChipCellsFormset(instance=clone)

        else:
            context['formset'] = AssayChipCellsFormset()

        # Cellsamples will always be the same
        context['cellsamples'] = cellsamples
        # Get protocols
        context['protocols'] = json.dumps({ item['id']: item['protocol'] for item in OrganModel.objects.all().values() })

        return context

    def form_valid(self, form):
        study = get_object_or_404(AssayRun, pk=self.kwargs['study_id'])
        form.instance.assay_run_id = study
        form.instance.group = study.group
        formset = AssayChipCellsFormset(self.request.POST, instance=form.instance, save_as_new=True)
        # get user via self.request.user
        if form.is_valid() and formset.is_valid():
            data = form.cleaned_data
            self.object = form.save()
            # Set restricted
            self.object.restricted = study.restricted
            self.object.modified_by = self.object.created_by = self.request.user
            # Save Chip Readout
            self.object.save()
            formset.save()
            if data['another']:
                form = self.form_class(instance=self.object,
                              initial={'success': True})
                return self.render_to_response(self.get_context_data(form=form))
            else:
                return redirect(self.object.get_absolute_url())
        else:
            return self.render_to_response(self.get_context_data(form=form))


class AssayChipSetupDetail(DetailRedirectMixin,DetailView):
    model = AssayChipSetup


# TODO IMPROVE METHOD FOR CLONING
class AssayChipSetupUpdate(ObjectGroupRequiredMixin, UpdateView):
    model = AssayChipSetup
    template_name = 'assays/assaychipsetup_add.html'
    form_class = AssayChipSetupForm

    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        form_class = self.get_form_class()
        form = self.get_form(form_class)

        # study = self.object.assay_run_id

        groups = self.request.user.groups.values_list('id', flat=True)
        cellsamples = CellSample.objects.filter(group__in=groups).order_by('-receipt_date').prefetch_related(
            'cell_type',
            'supplier',
        ).select_related('cell_type__cell_subtype')

        # Render form
        formset = AssayChipCellsFormset(instance=self.object)

        # Get protocols
        protocols = json.dumps({ item['id']: item['protocol'] for item in OrganModel.objects.all().values() })

        return self.render_to_response(
            self.get_context_data(form=form,
                                formset = formset,
                                cellsamples = cellsamples,
                                protocols = protocols,
                                update = True))

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()

        form = self.form_class(self.request.POST, instance=self.object)

        formset = AssayChipCellsFormset(self.request.POST, instance=form.instance)

        # TODO refactor redundant code here; testing for now

        study = self.object.assay_run_id

        groups = self.request.user.groups.values_list('id', flat=True)
        cellsamples = CellSample.objects.filter(group__in=groups).order_by('-receipt_date').prefetch_related(
            'cell_type',
            'supplier',
        ).select_related('cell_type__cell_subtype')

        form.instance.assay_run_id = study
        form.instance.group = study.group

        if form.is_valid() and formset.is_valid():
            data = form.cleaned_data
            # url_add = ''
            # if self.request.GET.get('setup', ''):
            #     url_add = '?setup=1'
            self.object = form.save()
            # TODO refactor original created by
            self.object.modified_by = self.request.user
            # Save overall setup result
            self.object.save()
            formset.instance = self.object
            formset.save()
            # THE TRACKING OF ANOTHER WAS TO CHECK IF SUBMIT AND CLONE WAS USED
            # NOW THE UPDATE PAGE WILL DISPLAY A HYPERLINK TO THE CLONE PAGE INSTEAD OF ACTUALLY PERFORMING A SUBMISSION FIRST
            # if data['another']:
            #     return redirect(self.object.get_absolute_url() + 'assaychipsetup/add/' + '?clone=' + str(self.object.id))
            # else:
            #     return redirect(self.object.get_absolute_url())
            return redirect(self.object.get_absolute_url())
                #return redirect(
                #    self.object.get_absolute_url() + url_add)
        else:

            # Get protocols
            protocols = json.dumps({ item['id']: item['protocol'] for item in OrganModel.objects.all().values() })

            return self.render_to_response(
            self.get_context_data(form=form,
                                formset = formset,
                                cellsamples = cellsamples,
                                protocols = protocols,
                                update = True))

class AssayChipSetupDelete(CreatorRequiredMixin, DeleteView):
    model = AssayChipSetup
    template_name = 'assays/assaychipsetup_delete.html'

    def get_success_url(self):
        return '/assays/' + str(self.object.assay_run_id.id)

    def get(self, request, *args, **kwargs):
        self.object = self.get_object()

        context = self.get_context_data()

        context['readouts'] = AssayChipReadout.objects.filter(chip_setup=self.object)
        context['results'] = AssayChipTestResult.objects.filter(chip_readout=context['readouts'])

        return self.render_to_response(context)


# Class based views for readouts
class AssayChipReadoutList(LoginRequiredMixin, ListView):
    model = AssayChipReadout

    def get_queryset(self):
        readouts = AssayChipReadout.objects.filter(chip_setup__assay_run_id__restricted=False).prefetch_related(
            'chip_setup', 'created_by', 'group').select_related('chip_setup__compound',
                                                                   'chip_setup__unit') | AssayChipReadout.objects.filter(
            chip_setup__assay_run_id__group__in=self.request.user.groups.all()).prefetch_related('chip_setup',
                                                                                                 'created_by', 'group').select_related(
            'chip_setup__compound', 'chip_setup__unit')

        related_assays = AssayChipReadoutAssay.objects.filter(readout_id__in=readouts).prefetch_related('readout_id','assay_id')
        related_assays_map = {}

        for assay in related_assays:
            # start appending to a list keyed by the readout ID for all related images
            related_assays_map.setdefault(assay.readout_id.id, []).append(assay)

        for readout in readouts:
            # set an attribute on the readout that is the list created above
            readout.related_assays = related_assays_map.get(readout.id)

        return readouts


ACRAFormSet = inlineformset_factory(AssayChipReadout, AssayChipReadoutAssay, formset=AssayChipReadoutInlineFormset,
                                    extra=1)


class AssayChipReadoutAdd(StudyGroupRequiredMixin, CreateView):
    template_name = 'assays/assaychipreadout_add.html'
    form_class = AssayChipReadoutForm

    def get_form(self, form_class):
        study = get_object_or_404(AssayRun, pk=self.kwargs['study_id'])
        current = None
        if self.request.method == 'POST':
            return form_class(study, current, self.request.POST, self.request.FILES)
        elif self.request.GET.get('clone',''):
            pk = int(self.request.GET.get('clone',''))
            clone = get_object_or_404(AssayChipReadout, pk=pk)
            form = form_class(study, current, instance=clone,
                              initial={'file': None})
            # We do not want to keep the file (setup automatically excluded)
            return form
        else:
            return form_class(study, current)

    def get_context_data(self, **kwargs):
        context = super(AssayChipReadoutAdd, self).get_context_data(**kwargs)
        if self.request.POST:
            context['formset'] = ACRAFormSet(self.request.POST, self.request.FILES)
        elif self.request.GET.get('clone',''):
            pk = int(self.request.GET.get('clone',''))
            clone = get_object_or_404(AssayChipReadout, pk=pk)
            context['formset'] = ACRAFormSet(instance=clone)
        else:
            context['formset'] = ACRAFormSet()

        return context

    def form_valid(self, form):
        study = get_object_or_404(AssayRun, pk=self.kwargs['study_id'])
        form.instance.group = study.group
        formset = ACRAFormSet(self.request.POST, self.request.FILES, instance=form.instance, save_as_new=True)
        # get user via self.request.user
        if form.is_valid() and formset.is_valid():
            data = form.cleaned_data

            # Get headers
            headers = int(data.get('headers'))

            self.object = form.save()
            # Set restricted
            self.object.restricted = study.restricted
            self.object.modified_by = self.object.created_by = self.request.user
            # Save Chip Readout
            self.object.save()
            ### TERRIBLE SOLUTION TESTING ###
            # for assay in formset:
            #     assay.instance.readout_id_id = self.object.id
            ### TERRIBLE SOLUTION TESTING
            formset.save()
            if formset.files.get('file',''):
                file = formset.files.get('file','')
                parseChipCSV(self.object, file, headers)
            if data['another']:
                form = self.form_class(study, None, instance=self.object,
                              initial={'file': None, 'success': True})
                return self.render_to_response(self.get_context_data(form=form))
            else:
                return redirect(self.object.get_absolute_url())
        else:
            return self.render_to_response(self.get_context_data(form=form))

    # Redirect when there are no available setups
    def render_to_response(self, context):
        # TODO REFACTOR
        study = get_object_or_404(AssayRun, pk=self.kwargs['study_id'])
        exclude_list = AssayChipReadout.objects.filter(chip_setup__isnull=False).values_list('chip_setup', flat=True)
        setups = AssayChipSetup.objects.filter(assay_run_id=study).prefetch_related(
            'assay_run_id', 'device',
            'compound', 'unit',
            'created_by').exclude(id__in=list(set(exclude_list)))
        if not setups:
            return redirect('/assays/'+str(study.id))

        return super(AssayChipReadoutAdd, self).render_to_response(context)


class AssayChipReadoutDetail(DetailRedirectMixin, DetailView):
    model = AssayChipReadout

class AssayChipReadoutUpdate(ObjectGroupRequiredMixin, UpdateView):
    model = AssayChipReadout
    template_name = 'assays/assaychipreadout_add.html'
    form_class = AssayChipReadoutForm

    def get_form(self, form_class):
        study = self.object.chip_setup.assay_run_id
        current = self.object.chip_setup_id

        # If POST
        if self.request.method == 'POST':
            return form_class(study, current, self.request.POST, self.request.FILES, instance=self.get_object())
        # If GET
        else:
            return form_class(study, current, instance=self.get_object())

    def get(self, request, *args, **kwargs):
        form = self.get_form(self.form_class)

        # Render form
        formset = ACRAFormSet(instance=self.object)
        return self.render_to_response(
            self.get_context_data(form=form,
                                formset = formset,
                                update=True))

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()

        form = self.get_form(self.form_class)

        formset = ACRAFormSet(self.request.POST, self.request.FILES, instance=form.instance)

        if form.is_valid() and formset.is_valid():
            data = form.cleaned_data

            # Get headers
            headers = int(data.get('headers'))

            self.object = form.save()
            self.object.modified_by = self.request.user
            # Save overall readout result
            self.object.save()
            formset.instance = self.object
            formset.save()
            # Save file if it exists
            if formset.files.get('file',''):
                file = formset.files.get('file','')
                parseChipCSV(self.object, file, headers)
            # Clear data if clear is checked
            if self.request.POST.get('file-clear',''):
                removeExistingChip(self.object)
            # Otherwise do nothing (the file remained the same)
            return redirect(self.object.get_absolute_url())
        else:
            return self.render_to_response(
            self.get_context_data(form=form,
                                formset = formset,
                                update=True))


class AssayChipReadoutDelete(CreatorRequiredMixin, DeleteView):
    model = AssayChipReadout
    template_name = 'assays/assaychipreadout_delete.html'

    def get_success_url(self):
        return '/assays/' + str(self.object.chip_setup.assay_run_id.id)

    def get(self, request, *args, **kwargs):
        self.object = self.get_object()

        context = self.get_context_data()

        context['results'] = AssayChipTestResult.objects.filter(chip_readout=self.object)

        return self.render_to_response(context)


# Class-based views for test results
class AssayChipTestResultList(LoginRequiredMixin, ListView):
    # model = AssayChipTestResult
    template_name = 'assays/assaychiptestresult_list.html'

    def get_queryset(self):
        initial_query = AssayChipResult.objects.prefetch_related('assay_name', 'assay_result', 'result_function',
                                                             'result_type',
                                                             'test_unit').select_related('assay_result__chip_readout',
                                                                                         'assay_result__chip_readout__chip_setup',
                                                                                         'assay_result__chip_readout__chip_setup__compound',
                                                                                         'assay_result__chip_readout__chip_setup__unit',
                                                                                         'assay_result__chip_readout__chip_setup__assay_run_id',
                                                                                         'assay_name__assay_id',
                                                                                         'assay_result__created_by',
                                                                                         'assay_result__group')

        return initial_query.filter(assay_result__chip_readout__chip_setup__assay_run_id__restricted=False) | \
               initial_query.filter(assay_result__chip_readout__chip_setup__assay_run_id__group__in=self.request.user.groups.all())


TestResultFormSet = inlineformset_factory(AssayChipTestResult, AssayChipResult, formset=TestResultInlineFormset, extra=1,
                                          widgets={'value': forms.NumberInput(attrs={'style': 'width:100px;', }), })


class AssayChipTestResultAdd(StudyGroupRequiredMixin, CreateView):
    template_name = 'assays/assaychiptestresult_add.html'
    form_class = AssayChipResultForm

    def get_form(self, form_class):
        study = get_object_or_404(AssayRun, pk=self.kwargs['study_id'])
        current = None

        if self.request.method == 'POST':
            return form_class(study, current, self.request.POST)
        else:
            return form_class(study, current)

    def get_context_data(self, **kwargs):
        context = super(AssayChipTestResultAdd, self).get_context_data(**kwargs)
        if self.request.POST:
            context['formset'] = TestResultFormSet(self.request.POST)
        else:
            context['formset'] = TestResultFormSet()
        return context

    def form_valid(self, form):
        study = get_object_or_404(AssayRun, pk=self.kwargs['study_id'])
        form.instance.group = study.group
        context = self.get_context_data()
        formset = context['formset']
        # get user via self.request.user
        if form.is_valid() and formset.is_valid():
            self.object = form.save()
            # Set restricted
            self.object.restricted = study.restricted
            self.object.modified_by = self.object.created_by = self.request.user
            # Save overall test result
            self.object.save()
            formset.instance = self.object
            formset.save()
            return redirect(self.object.get_absolute_url())  # assuming your model has ``get_absolute_url`` defined.
        else:
            return self.render_to_response(self.get_context_data(form=form))

    # Redirect when there are no available setups
    # TODO REFACTOR
    def render_to_response(self, context):
        study = get_object_or_404(AssayRun, pk=self.kwargs['study_id'])
        exclude_list = AssayChipTestResult.objects.filter(chip_readout__isnull=False).values_list('chip_readout', flat=True)
        readouts = AssayChipReadout.objects.filter(chip_setup__assay_run_id=study).exclude(id__in=list(set(exclude_list)))

        if not readouts:
            return redirect('/assays/'+str(study.id))

        return super(AssayChipTestResultAdd, self).render_to_response(context)


class AssayChipTestResultDetail(DetailRedirectMixin, DetailView):
    model = AssayChipTestResult


class AssayChipTestResultUpdate(ObjectGroupRequiredMixin, UpdateView):
    model = AssayChipTestResult
    template_name = 'assays/assaychiptestresult_add.html'
    form_class = AssayChipResultForm

    def get_form(self, form_class):
        study = self.object.chip_readout.chip_setup.assay_run_id
        current = self.object.chip_readout_id

        # If POST
        if self.request.method == 'POST':
            return form_class(study, current, self.request.POST, instance=self.get_object())
        # If GET
        else:
            return form_class(study, current, instance=self.get_object())

    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        form = self.get_form(self.form_class)

        # Render form
        formset = TestResultFormSet(instance=self.object)
        return self.render_to_response(
            self.get_context_data(form=form,
                                  formset = formset,
                                  update = True))

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()

        form = self.get_form(self.form_class)

        formset = TestResultFormSet(self.request.POST, instance=form.instance)

        # TODO refactor redundant code here; testing for now

        study = self.object.chip_readout.chip_setup.assay_run_id

        form.instance.group = study.group
        # Setting restricted in the form does not work as it is not part of the form
        # form.instance.restricted = study.restricted

        if form.is_valid() and formset.is_valid():
            self.object = form.save()
            # TODO refactor original created by
            self.object.modified_by = self.request.user
            # Save overall test result
            self.object.save()
            formset.instance = self.object
            formset.save()
            return redirect(self.object.get_absolute_url())  # assuming your model has ``get_absolute_url`` defined.
        else:
            return self.render_to_response(
            self.get_context_data(form=form,
                                  formset = formset,
                                  update = True))


class AssayChipTestResultDelete(CreatorRequiredMixin, DeleteView):
    model = AssayChipTestResult
    template_name = 'assays/assaychiptestresult_delete.html'

    def get_success_url(self):
        return '/assays/' + str(self.object.chip_readout.chip_setup.assay_run_id.id)


# Class-based views for study configuration
class StudyConfigurationList(LoginRequiredMixin, ListView):
    model = StudyConfiguration
    template_name = 'assays/studyconfiguration_list.html'


# FormSet for Study Models
StudyModelFormSet = inlineformset_factory(StudyConfiguration, StudyModel, extra=1,
                                              widgets={
                                              'label': forms.TextInput(attrs={'size': 2, }),
                                              'sequence_number': forms.TextInput(attrs={'size': 2}), })


class StudyConfigurationAdd(OneGroupRequiredMixin, CreateView):
    template_name = 'assays/studyconfiguration_add.html'
    form_class = StudyConfigurationForm

    def get_context_data(self, **kwargs):
        context = super(StudyConfigurationAdd, self).get_context_data(**kwargs)

        if self.request.POST:
            context['formset'] = StudyModelFormSet(self.request.POST)
        else:
            context['formset'] = StudyModelFormSet()

        return context

    def form_valid(self, form):
        context = self.get_context_data()
        formset = context['formset']
        # get user via self.request.user
        if form.is_valid() and formset.is_valid():
            self.object = form.save()
            self.object.modified_by = self.object.created_by = self.request.user
            # Save overall configuration
            self.object.save()
            formset.instance = self.object
            formset.save()
            return redirect(self.object.get_absolute_url())  # assuming your model has ``get_absolute_url`` defined.
        else:
            return self.render_to_response(self.get_context_data(form=form))


class StudyConfigurationUpdate(OneGroupRequiredMixin, UpdateView):
    model = StudyConfiguration
    template_name = 'assays/studyconfiguration_add.html'
    form_class = StudyConfigurationForm

    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        form_class = self.get_form_class()
        form = self.get_form(form_class)

        # Render form
        formset = StudyModelFormSet(instance=self.object)
        return self.render_to_response(
            self.get_context_data(form=form,
                                formset = formset,
                                update = True))

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()

        form = self.form_class(self.request.POST, instance=self.object)

        formset = StudyModelFormSet(self.request.POST, instance=form.instance)

        if form.is_valid() and formset.is_valid():
            self.object = form.save()
            # TODO refactor original created by
            self.object.modified_by = self.request.user
            # Save overall test result
            self.object.save()
            formset.instance = self.object
            formset.save()
            return redirect(self.object.get_absolute_url())  # assuming your model has ``get_absolute_url`` defined.
        else:
            return self.render_to_response(
            self.get_context_data(form=form,
                                formset = formset,
                                update = True))


# Class-based views for LAYOUTS
class AssayLayoutList(LoginRequiredMixin, ListView):
    model = AssayLayout

    def get_queryset(self):
        # Not bothering with restricted at the moment
        # return AssayLayout.objects.filter(restricted=False).prefetch_related('created_by', 'group', 'device') | AssayLayout.objects.filter(
        #     group__in=self.request.user.groups.all()).prefetch_related('created_by', 'group', 'device')
        return AssayLayout.objects.filter(group__in=self.request.user.groups.all()).prefetch_related('created_by', 'group', 'device')

class AssayLayoutAdd(OneGroupRequiredMixin, CreateView):
    model = AssayLayout
    form_class = AssayLayoutForm
    template_name = 'assays/assaylayout_add.html'

    def get_form(self,form_class):
        # Get group selection possibilities
        groups = self.request.user.groups.filter(
            ~Q(name__contains="Add ") & ~Q(name__contains="Change ") & ~Q(name__contains="Delete "))

        # If POST
        if self.request.method == 'POST':
            return form_class(groups, self.request.POST)
        # If GET
        else:
            return form_class(groups)

    # Test form validity
    def form_valid(self, form):
        if form.is_valid():
            # Confirm form and get object
            self.object = form.save()
            # Save assay layout
            save_assay_layout(self.request, self.object, form, False)
            return redirect(
                self.object.get_absolute_url())

        else:
            return self.render_to_response(self.get_context_data(form=form))


# TODO Assay Layout Detail does not currently exist (deemed lower priority)
# class AssayLayoutDetail(DetailRedirectMixin, DetailView):
#     model = AssayLayout


class AssayLayoutUpdate(ObjectGroupRequiredMixin, UpdateView):
    model = AssayLayout
    form_class = AssayLayoutForm
    template_name = 'assays/assaylayout_add.html'

    def get_form(self,form_class):
        # Get group selection possibilities
        groups = self.request.user.groups.filter(
            ~Q(name__contains="Add ") & ~Q(name__contains="Change ") & ~Q(name__contains="Delete "))

        # If POST
        if self.request.method == 'POST':
            return form_class(groups, self.request.POST, instance=self.get_object())
        # If GET
        else:
            return form_class(groups, instance=self.get_object())

    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        form = self.get_form(self.form_class)

        return self.render_to_response(
            self.get_context_data(form=form,
                                  update=True))

    def post(self, request, *args, **kwargs):
        form = self.get_form(self.form_class)

        if form.is_valid():
            # Confirm form and get object
            self.object = form.save()
            # Save assay layout
            save_assay_layout(self.request, self.object, form, True)
            return redirect(self.object.get_absolute_url())

        else:
            return self.render_to_response(
            self.get_context_data(form=form,
                                  update=True))


# TODO ADD CONTEXT
class AssayLayoutDelete(CreatorRequiredMixin, DeleteView):
    model = AssayLayout
    template_name = 'assays/assaylayout_delete.html'

    def get_success_url(self):
        return '/assays/assaylayout/'


# Class-based views for LAYOUTS
class AssayPlateSetupList(LoginRequiredMixin, ListView):
    model = AssayPlateSetup

    def get_queryset(self):
        return AssayPlateSetup.objects.filter(restricted=False).prefetch_related('created_by', 'group', 'assay_run_id', 'assay_layout') | AssayPlateSetup.objects.filter(
            group__in=self.request.user.groups.all()).prefetch_related('created_by', 'group', 'assay_run_id', 'assay_layout')

# Formset for plate cells
AssayPlateCellsFormset = inlineformset_factory(AssayPlateSetup, AssayPlateCells, formset=AssayPlateCellsInlineFormset,
                                              extra=1,
                                              widgets={
                                              'cellsample_density': forms.NumberInput(attrs={'style': 'width:100px;', }),
                                              'cell_passage': forms.TextInput(attrs={'size': 5}), })


# VIEWS FOR ASSAY PLATE (DEVICE) SETUP
class AssayPlateSetupAdd(StudyGroupRequiredMixin, CreateView):
    model = AssayPlateSetup
    form_class = AssayPlateSetupForm
    template_name = 'assays/assayplatesetup_add.html'

    def get_form(self, form_class):
        if self.request.method == 'POST':
            return form_class(self.request.POST)
        elif self.request.GET.get('clone',''):
            pk = int(self.request.GET.get('clone',''))
            clone = get_object_or_404(AssayPlateSetup, pk=pk)
            return form_class(instance=clone)
        else:
            return form_class()

    def get_context_data(self, **kwargs):
        groups = self.request.user.groups.values_list('id', flat=True)
        cellsamples = CellSample.objects.filter(group__in=groups).order_by('-receipt_date').prefetch_related(
            'cell_type',
            'supplier',
        ).select_related('cell_type__cell_subtype')
        context = super(AssayPlateSetupAdd, self).get_context_data(**kwargs)

        if self.request.POST:
            context['formset'] = AssayPlateCellsFormset(self.request.POST)
        elif self.request.GET.get('clone',''):
            pk = int(self.request.GET.get('clone',''))
            clone = get_object_or_404(AssayPlateSetup, pk=pk)
            context['formset'] = AssayPlateCellsFormset(instance=clone)
        else:
            context['formset'] = AssayPlateCellsFormset()

        # Cellsamples will always be the same
        context['cellsamples'] = cellsamples

        return context

    def form_valid(self, form):
        study = get_object_or_404(AssayRun, pk=self.kwargs['study_id'])
        form.instance.assay_run_id = study
        form.instance.group = study.group
        formset = AssayPlateCellsFormset(self.request.POST, instance=form.instance, save_as_new=True)
        # get user via self.request.user
        if form.is_valid() and formset.is_valid():
            data = form.cleaned_data
            self.object = form.save()
            # Set restricted
            self.object.restricted = study.restricted
            self.object.modified_by = self.object.created_by = self.request.user
            # Save Plate Setup
            self.object.save()
            formset.save()
            if data['another']:
                form = self.form_class(instance=self.object,
                              initial={'success': True})
                return self.render_to_response(self.get_context_data(form=form))
            else:
                return redirect(self.object.get_absolute_url())
        else:
            return self.render_to_response(self.get_context_data(form=form))


# TODO Assay Layout Detail does not currently exist (deemed lower priority)
class AssayPlateSetupDetail(DetailRedirectMixin, DetailView):
    model = AssayPlateSetup


# TODO ADD ADDITIONAL CONTEXT
class AssayPlateSetupUpdate(ObjectGroupRequiredMixin, UpdateView):
    model = AssayPlateSetup
    form_class = AssayPlateSetupForm
    template_name = 'assays/assayplatesetup_add.html'

    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        form_class = self.get_form_class()
        form = self.get_form(form_class)

        # study = self.object.assay_run_id

        groups = self.request.user.groups.values_list('id', flat=True)
        cellsamples = CellSample.objects.filter(group__in=groups).order_by('-receipt_date').prefetch_related(
            'cell_type',
            'supplier',
        ).select_related('cell_type__cell_subtype')

        # Render form
        formset = AssayPlateCellsFormset(instance=self.object)

        return self.render_to_response(
            self.get_context_data(form=form,
                                formset = formset,
                                cellsamples = cellsamples,
                                update = True))

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()

        form = self.form_class(self.request.POST, instance=self.object)

        formset = AssayPlateCellsFormset(self.request.POST, instance=form.instance)

        # TODO refactor redundant code here; testing for now

        study = self.object.assay_run_id

        groups = self.request.user.groups.values_list('id', flat=True)
        cellsamples = CellSample.objects.filter(group__in=groups).order_by('-receipt_date').prefetch_related(
            'cell_type',
            'supplier',
        ).select_related('cell_type__cell_subtype')

        form.instance.assay_run_id = study
        form.instance.group = study.group

        if form.is_valid() and formset.is_valid():
            self.object = form.save()
            self.object.modified_by = self.request.user
            # Save overall setup result
            self.object.save()
            formset.instance = self.object
            formset.save()
            return redirect(self.object.get_absolute_url())
        else:

            return self.render_to_response(
            self.get_context_data(form=form,
                                formset = formset,
                                cellsamples = cellsamples,
                                update = True))


# TODO ADD CONTEXT
class AssayPlateSetupDelete(CreatorRequiredMixin, DeleteView):
    model = AssayPlateSetup
    template_name = 'assays/assayplatesetup_delete.html'

    def get_success_url(self):
        return '/assays/' + str(self.object.assay_run_id.id)


# Class based views for readouts
class AssayPlateReadoutList(LoginRequiredMixin, ListView):
    model = AssayPlateReadout

    def get_queryset(self):
        readouts = AssayPlateReadout.objects.filter(setup__assay_run_id__restricted=False).prefetch_related(
            'setup', 'created_by', 'group') | AssayPlateReadout.objects.filter(
            setup__assay_run_id__group__in=self.request.user.groups.all()).prefetch_related('setup',
                                                                                            'created_by', 'group')

        related_assays = AssayPlateReadoutAssay.objects.filter(readout_id__in=readouts).prefetch_related('readout_id',
                                                                                                         'assay_id')
        related_assays_map = {}

        for assay in related_assays:
            # start appending to a list keyed by the readout ID for all related images
            related_assays_map.setdefault(assay.readout_id.id, []).append(assay)

        for readout in readouts:
            # set an attribute on the readout that is the list created above
            readout.related_assays = related_assays_map.get(readout.id)

        return readouts


APRAFormSet = inlineformset_factory(AssayPlateReadout, AssayPlateReadoutAssay, formset=AssayPlateReadoutInlineFormset,
                                    extra=1)


class AssayPlateReadoutAdd(StudyGroupRequiredMixin, CreateView):
    template_name = 'assays/assayplatereadout_add.html'
    form_class = AssayPlateReadoutForm

    def get_form(self, form_class):
        study = get_object_or_404(AssayRun, pk=self.kwargs['study_id'])
        current = None
        if self.request.method == 'POST':
            return form_class(study, current, self.request.POST, self.request.FILES)
        elif self.request.GET.get('clone',''):
            pk = int(self.request.GET.get('clone',''))
            clone = get_object_or_404(AssayPlateReadout, pk=pk)
            return form_class(study, current, instance=clone,
                              initial={'file': None})
            # We do not want to keep the file (setup automatically excluded))
        else:
            return form_class(study, current)

    def get_context_data(self, **kwargs):
        context = super(AssayPlateReadoutAdd, self).get_context_data(**kwargs)
        if self.request.POST:
            context['formset'] = APRAFormSet(self.request.POST, self.request.FILES)
        elif self.request.GET.get('clone',''):
            pk = int(self.request.GET.get('clone',''))
            clone = get_object_or_404(AssayPlateReadout, pk=pk)
            context['formset'] = APRAFormSet(instance=clone)
        else:
            context['formset'] = APRAFormSet()

        return context

    def form_valid(self, form):
        study = get_object_or_404(AssayRun, pk=self.kwargs['study_id'])
        form.instance.group = study.group
        formset = APRAFormSet(self.request.POST, self.request.FILES, instance=form.instance, save_as_new=True)
        # get user via self.request.user
        if form.is_valid() and formset.is_valid():
            data = form.cleaned_data

            # Get upload_type
            upload_type = data.get('upload_type')

            self.object = form.save()
            # Set restricted
            self.object.restricted = study.restricted
            self.object.modified_by = self.object.created_by = self.request.user
            # Save Chip Readout
            self.object.save()
            formset.save()
            if formset.files.get('file',''):
                file = formset.files.get('file','')
                parseReadoutCSV(self.object, file, upload_type)
            if data['another']:
                form = self.form_class(study, None, instance=self.object,
                              initial={'file': None, 'success': True})
                return self.render_to_response(self.get_context_data(form=form))
            else:
                return redirect(self.object.get_absolute_url())
        else:
            return self.render_to_response(self.get_context_data(form=form))

    # Redirect when there are no available setups
    # TODO REFACTOR
    def render_to_response(self, context):
        study = get_object_or_404(AssayRun, pk=self.kwargs['study_id'])
        exclude_list = AssayPlateReadout.objects.filter(setup__isnull=False).values_list('setup', flat=True)
        setups = AssayPlateSetup.objects.filter(assay_run_id=study).prefetch_related(
            'assay_run_id', 'assay_layout',
            'created_by').exclude(id__in=list(set(exclude_list)))

        if not setups:
            return redirect('/assays/'+str(study.id))

        return super(AssayPlateReadoutAdd, self).render_to_response(context)


# TODO ADD TEMPLATE
class AssayPlateReadoutDetail(DetailRedirectMixin, DetailView):
    model = AssayPlateReadout

class AssayPlateReadoutUpdate(ObjectGroupRequiredMixin, UpdateView):
    model = AssayPlateReadout
    template_name = 'assays/assayplatereadout_add.html'
    form_class = AssayPlateReadoutForm

    def get_form(self, form_class):
        study = self.object.setup.assay_run_id
        current = self.object.setup_id

        # If POST
        if self.request.method == 'POST':
            return form_class(study, current, self.request.POST, self.request.FILES, instance=self.get_object())
        # If GET
        else:
            return form_class(study, current, instance=self.get_object())

    def get(self, request, *args, **kwargs):
        form = self.get_form(self.form_class)

        # Render form
        formset = APRAFormSet(instance=self.object)
        return self.render_to_response(
            self.get_context_data(form=form,
                                formset = formset,
                                update=True))

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()

        form = self.get_form(self.form_class)

        formset = APRAFormSet(self.request.POST, self.request.FILES, instance=form.instance)

        study = self.object.setup.assay_run_id

        form.instance.group = study.group

        if form.is_valid() and formset.is_valid():
            data = form.cleaned_data

            # Get upload_type
            upload_type = data.get('upload_type')

            self.object = form.save()
            # TODO refactor original created by
            self.object.modified_by = self.request.user
            # Save overall readout result
            self.object.save()
            formset.instance = self.object
            formset.save()
            # Save file if it exists
            if formset.files.get('file',''):
                file = formset.files.get('file','')
                parseReadoutCSV(self.object, file, upload_type)
            # Clear data if clear is checked
            if self.request.POST.get('file-clear',''):
                removeExistingReadout(self.object)
            # Otherwise do nothing (the file remained the same)
            return redirect(self.object.get_absolute_url())
        else:
            return self.render_to_response(
            self.get_context_data(form=form,
                                formset = formset,
                                update=True))


# TODO ADD CONTEXT
class AssayPlateReadoutDelete(CreatorRequiredMixin, DeleteView):
    model = AssayPlateReadout
    template_name = 'assays/assayplatereadout_delete.html'

    def get_success_url(self):
        return '/assays/' + str(self.object.setup.assay_run_id.id)


# Class-based views for PLATE test results
class AssayPlateTestResultList(LoginRequiredMixin, ListView):
    # model = AssayChipTestResult
    template_name = 'assays/assayplatetestresult_list.html'

    def get_queryset(self):
        initial_query = AssayPlateResult.objects.prefetch_related('result_function','result_type',
                                                             'test_unit').select_related('assay_result__readout__setup__assay_run_id',
                                                                                         'assay_name__assay_id',
                                                                                         'assay_result__created_by',
                                                                                         'assay_result__group')

        return initial_query.filter(assay_result__readout__setup__assay_run_id__restricted=False) | \
               initial_query.filter(assay_result__readout__setup__assay_run_id__group__in=self.request.user.groups.all())


PlateTestResultFormSet = inlineformset_factory(AssayPlateTestResult, AssayPlateResult, formset=PlateTestResultInlineFormset, extra=1,
                                          widgets={'value': forms.NumberInput(attrs={'style': 'width:100px;', }), })


class AssayPlateTestResultAdd(StudyGroupRequiredMixin, CreateView):
    template_name = 'assays/assayplatetestresult_add.html'
    form_class = AssayPlateResultForm

    def get_form(self, form_class):
        study = get_object_or_404(AssayRun, pk=self.kwargs['study_id'])
        current = None

        if self.request.method == 'POST':
            return form_class(study, current, self.request.POST)
        else:
            return form_class(study, current)

    def get_context_data(self, **kwargs):
        context = super(AssayPlateTestResultAdd, self).get_context_data(**kwargs)
        if self.request.POST:
            context['formset'] = PlateTestResultFormSet(self.request.POST)
        else:
            context['formset'] = PlateTestResultFormSet()
        return context

    def form_valid(self, form):
        study = get_object_or_404(AssayRun, pk=self.kwargs['study_id'])
        form.instance.group = study.group
        context = self.get_context_data()
        formset = context['formset']
        # get user via self.request.user
        if form.is_valid() and formset.is_valid():
            self.object = form.save()
            # Set restricted
            self.object.restricted = study.restricted
            self.object.modified_by = self.object.created_by = self.request.user
            # Save overall test result
            self.object.save()
            formset.instance = self.object
            formset.save()
            return redirect(self.object.get_absolute_url())  # assuming your model has ``get_absolute_url`` defined.
        else:
            return self.render_to_response(self.get_context_data(form=form))

    # Redirect when there are no available setups
    # TODO REFACTOR
    def render_to_response(self, context):
        study = get_object_or_404(AssayRun, pk=self.kwargs['study_id'])
        exclude_list = AssayPlateTestResult.objects.filter(readout__isnull=False).values_list('readout', flat=True)
        readouts = AssayPlateReadout.objects.filter(setup__assay_run_id=study).exclude(id__in=list(set(exclude_list)))

        if not readouts:
            return redirect('/assays/'+str(study.id))

        return super(AssayPlateTestResultAdd, self).render_to_response(context)


class AssayPlateTestResultDetail(DetailRedirectMixin, DetailView):
    model = AssayPlateTestResult


class AssayPlateTestResultUpdate(ObjectGroupRequiredMixin, UpdateView):
    model = AssayPlateTestResult
    template_name = 'assays/assayplatetestresult_add.html'
    form_class = AssayPlateResultForm

    def get_form(self, form_class):
        study = self.object.readout.setup.assay_run_id
        current = self.object.readout_id

        # If POST
        if self.request.method == 'POST':
            return form_class(study, current, self.request.POST, instance=self.get_object())
        # If GET
        else:
            return form_class(study, current, instance=self.get_object())

    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        form = self.get_form(self.form_class)

        # Render form
        formset = PlateTestResultFormSet(instance=self.object)
        return self.render_to_response(
            self.get_context_data(form=form,
                                  formset = formset,
                                  update = True))

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()

        form = self.get_form(self.form_class)
        formset = PlateTestResultFormSet(self.request.POST, instance=form.instance)

        study = self.object.readout.setup.assay_run_id

        form.instance.group = study.group
        # Setting restricted in the form does not work as it is not part of the form
        # form.instance.restricted = study.restricted

        if form.is_valid() and formset.is_valid():
            self.object = form.save()
            # TODO refactor original created by
            self.object.modified_by = self.request.user
            # Save overall test result
            self.object.save()
            formset.instance = self.object
            formset.save()
            return redirect(self.object.get_absolute_url())  # assuming your model has ``get_absolute_url`` defined.
        else:
            return self.render_to_response(
            self.get_context_data(form=form,
                                  formset = formset,
                                  update = True))


class AssayPlateTestResultDelete(CreatorRequiredMixin, DeleteView):
    model = AssayPlateTestResult
    template_name = 'assays/assayplatetestresult_delete.html'

    def get_success_url(self):
        return '/assays/' + str(self.object.readout.setup.assay_run_id.id)
