from django import forms
from django.forms.models import BaseInlineFormSet
from assays.models import *
from compounds.models import Compound
from mps.forms import SignOffMixin
# Use regular expressions for a string split at one point
import re
import string

from .utils import validate_file, get_chip_details, get_plate_details

# TODO REFACTOR WHITTLING TO BE HERE IN LIEU OF VIEW
# TODO REFACTOR FK QUERYSETS TO AVOID N+1

# These are all of the tracking fields
tracking = ('created_by', 'created_on', 'modified_on', 'modified_by', 'signed_off_by', 'signed_off_date')
# Excluding restricted is likewise useful
restricted = ('restricted',)
# Group
group = ('group',)

# Overwrite options
OVERWRITE_OPTIONS = forms.ChoiceField(
    choices=(
        ('keep_conflicting_data', 'Keep Confilicting Data as Replicate'),
        ('mark_conflicting_data', 'Mark Conflicting Data'),
        ('mark_all_old_data', 'Mark All Old Data'),
        ('delete_conflicting_data', 'Delete Conflicting Data'),
        ('delete_all_old_data', 'Delete All Old Data')
    ),
    initial='Keep Confilicting Data as Replicate'
)


# SUBJECT TO CHANGE
class CloneableForm(forms.ModelForm):
    """Convenience class for adding clone fields"""
    another = forms.BooleanField(required=False, initial=False)
    success = forms.BooleanField(required=False, initial=False)


# SUBJECT TO CHANGE AND REQUIRES TESTING
class CloneableBaseInlineFormSet(BaseInlineFormSet):
    """Overrides create form for the sake of using save_as_new for the purpose of cloning"""
    def _construct_form(self, i, **kwargs):
        form = super(BaseInlineFormSet, self)._construct_form(i, **kwargs)
        # Removed code below
        # if self.save_as_new:
        #     # Remove the primary key from the form's data, we are only
        #     # creating new instances
        #     form.data[form.add_prefix(self._pk_field.name)] = None
        #
        #     # Remove the foreign key from the form's data
        #     form.data[form.add_prefix(self.fk.name)] = None

        # Set the fk value here so that the form can do its validation.
        fk_value = self.instance.pk

        if self.fk.rel.field_name != self.fk.rel.to._meta.pk.name:
            fk_value = getattr(self.instance, self.fk.rel.field_name)
            fk_value = getattr(fk_value, 'pk', fk_value)
        setattr(form.instance, self.fk.get_attname(), fk_value)

        return form


class AssayRunForm(SignOffMixin, forms.ModelForm):
    """Frontend Form for Studies"""
    def __init__(self, groups, *args, **kwargs):
        """Init the Study Form

        Parameters:
        groups -- a queryset of groups (allows us to avoid N+1 problem)
        """
        super(AssayRunForm, self).__init__(*args, **kwargs)
        self.fields['group'].queryset = groups

    class Meta(object):
        model = AssayRun
        widgets = {
            'assay_run_id': forms.Textarea(attrs={'rows': 1}),
            'name': forms.Textarea(attrs={'rows': 1}),
            'description': forms.Textarea(attrs={'rows': 3}),
        }
        exclude = tracking

    def clean(self):
        """Checks for at least one study type and deformed assay_run_ids"""

        # clean the form data, before validation
        data = super(AssayRunForm, self).clean()

        if not any([data['toxicity'], data['efficacy'], data['disease'], data['cell_characterization']]):
            raise forms.ValidationError('Please select at least one study type')

        if data['assay_run_id'].startswith('-'):
            raise forms.ValidationError('Error with assay_run_id; please try again')


class StudySupportingDataInlineFormset(BaseInlineFormSet):
    """Form for Study Supporting Data (as part of an inline)"""
    class Meta(object):
        model = StudySupportingData
        exclude = ('',)


class AssayChipResultForm(SignOffMixin, forms.ModelForm):
    """Frontend form for Chip Test Results"""
    def __init__(self, study, current, *args, **kwargs):
        """Init the Chip Test Results Form

        Parameters:
        study -- the study the result is from (to filter Readout dropdown)
        current -- the currently selected readout (if the Test Result is being updated)
        """
        super(AssayChipResultForm, self).__init__(*args, **kwargs)
        exclude_list = AssayChipTestResult.objects.filter(
            chip_readout__isnull=False
        ).values_list(
            'chip_readout',
            flat=True
        )
        readouts = AssayChipReadout.objects.filter(
            chip_setup__assay_run_id=study
        ).exclude(
            id__in=list(set(exclude_list))
        )
        if current:
            readouts = readouts | AssayChipReadout.objects.filter(pk=current)
        readouts = readouts.prefetch_related('chip_setup', 'chip_setup__unit', 'chip_setup__compound')
        self.fields['chip_readout'].queryset = readouts

    class Meta(object):
        model = AssayChipTestResult
        widgets = {
            'summary': forms.Textarea(attrs={'cols': 75, 'rows': 3}),
        }
        exclude = group + tracking + restricted


class AssayChipReadoutForm(SignOffMixin, CloneableForm):
    """Frontend form for Chip Readouts"""
    overwrite_option = OVERWRITE_OPTIONS

    def __init__(self, study, current, *args, **kwargs):
        """Init the Chip Readout Form

        Parameters:
        study -- the study the readout is from (to filter setup dropdown)
        current -- the currently selected setup (if the Readout is being updated)

        Additional fields (not part of model):
        headers -- specifies the number of header lines in the uploaded csv
        """
        super(AssayChipReadoutForm, self).__init__(*args, **kwargs)
        self.fields['timeunit'].queryset = PhysicalUnits.objects.filter(
            unit_type__unit_type='Time'
        ).order_by('scale_factor')
        exclude_list = AssayChipReadout.objects.filter(chip_setup__isnull=False).values_list('chip_setup', flat=True)
        setups = AssayChipSetup.objects.filter(assay_run_id=study).prefetch_related(
            'assay_run_id', 'device',
            'compound', 'unit',
            'created_by').exclude(id__in=list(set(exclude_list)))
        if current:
            setups = setups | AssayChipSetup.objects.filter(pk=current)
        self.fields['chip_setup'].queryset = setups

    # Specifies the number of headers in the uploaded csv
    headers = forms.CharField(required=True, initial=1)

    class Meta(object):
        model = AssayChipReadout
        widgets = {
            'notebook_page': forms.NumberInput(attrs={'style': 'width:50px;'}),
            'treatment_time_length': forms.NumberInput(attrs={'style': 'width:174px;'}),
            'notes': forms.Textarea(attrs={'cols': 50, 'rows': 3}),
        }
        exclude = group + tracking + restricted

    # Set chip setup to unique instead of throwing error in validation


class AssayChipSetupForm(SignOffMixin, CloneableForm):
    """Frontend form for Chip Setups"""
    def __init__(self, *args, **kwargs):
        """Init Chip Setup Form

        Filters physical units to include only concentrations and %
        Filters devices to only include devices labelled as "chips"
        """
        super(AssayChipSetupForm, self).__init__(*args, **kwargs)
        # Filter on concentration but make a special exception for percent (%)
        self.fields['unit'].queryset = PhysicalUnits.objects.filter(
            unit_type__unit_type='Concentration'
        ).order_by(
            'base_unit',
            'scale_factor'
        ) | PhysicalUnits.objects.filter(unit='%')
        # Filter devices to be only microchips (or "chips" like the venous system)
        self.fields['device'].queryset = Microdevice.objects.filter(device_type='chip')

    class Meta(object):
        model = AssayChipSetup
        widgets = {
            'concentration': forms.NumberInput(attrs={'style': 'width:50px;'}),
            'notebook_page': forms.NumberInput(attrs={'style': 'width:50px;'}),
            'notes': forms.Textarea(attrs={'cols': 50, 'rows': 3}),
            'variance': forms.Textarea(attrs={'cols': 50, 'rows': 2}),
        }
        # Assay Run ID is always bound to the parent Study
        exclude = ('assay_run_id', 'group') + tracking + restricted

    def clean(self):
        """Cleans the Chip Setup Form

        Ensures the the name is unique in the current study
        Ensures that the data for a compound is complete
        Prevents changes to the chip if data has been uploaded (avoiding conflicts between data and entries)
        """
        super(forms.ModelForm, self).clean()

        # Make sure the barcode/ID is unique in the study
        if AssayChipSetup.objects.filter(
                assay_run_id=self.instance.assay_run_id,
                assay_chip_id=self.cleaned_data.get('assay_chip_id')
        ).exclude(id=self.instance.id):
            raise forms.ValidationError({'assay_chip_id': ['ID/Barcode must be unique within study.']})

        # Check to see if compound data is complete if: 1.) compound test type 2.) compound is selected
        current_type = self.cleaned_data.get('chip_test_type', '')
        compound = self.cleaned_data.get('compound', '')
        concentration = self.cleaned_data.get('concentration', '')
        unit = self.cleaned_data.get('unit', '')
        if current_type == 'compound' and not all([compound, concentration, unit]) \
                or (compound and not all([concentration, unit])):
            raise forms.ValidationError('Please complete all data for compound.')

        # RENAMING CHIPS WITH DATA IS NOW ALLOWED
        # Check to see if data has been uploaded for this setup
        # Prevent changing chip id if this is the case
        # Get readouts
        # readout = AssayChipReadout.objects.filter(chip_setup=self.instance)
        # if readout:
        #     if AssayChipRawData.objects.filter(assay_chip_id=readout) \
        #             and self.cleaned_data.get('assay_chip_id') != self.instance.assay_chip_id:
        #         raise forms.ValidationError(
        #             {'assay_chip_id': ['Chip ID/Barcode cannot be changed after data has been uploaded.']}
        #         )


class AssayChipCellsInlineFormset(CloneableBaseInlineFormSet):
    """Frontend Inline Formset for Chip Cells"""
    class Meta(object):
        model = AssayChipCells
        exclude = ('',)

    # def clean(self):
    #     forms_data = [f for f in self.forms if f.cleaned_data and not f.cleaned_data.get('DELETE', False)]
    #
    #     #Does not require a minimum number of cellsamples at the moment
    #     Number of cellsamples
    #     cellsamples = 0
    #     for form in forms_data:
    #         try:
    #             if form.cleaned_data:
    #                 cellsamples += 1
    #         except AttributeError:
    #             pass
    #     if cellsamples < 1:
    #         raise forms.ValidationError('You must have at least one cellsample.')


class ChipTestResultInlineFormset(BaseInlineFormSet):
    """Frontend inline formset for Individual Chip Results"""
    def __init__(self, *args, **kwargs):
        """Init the Chip Result Inline

        Filters units so that only those marked 'test' appear in the dropdown
        """
        super(ChipTestResultInlineFormset, self).__init__(*args, **kwargs)
        unit_queryset = PhysicalUnits.objects.filter(
            availability__contains='test'
        ).order_by('base_unit', 'scale_factor')
        for form in self.forms:
            form.fields['test_unit'].queryset = unit_queryset

    class Meta(object):
        model = AssayChipResult
        exclude = ('',)

    def clean(self):
        """Clean Result Inline

        Prevents submission with no results
        """
        forms_data = [f for f in self.forms if f.cleaned_data and not f.cleaned_data.get('DELETE', False)]

        # Number of results
        results = 0
        for form in forms_data:
            try:
                if form.cleaned_data:
                    results += 1
            except AttributeError:
                pass
        if results < 1:
            raise forms.ValidationError('You must have at least one result.')


class StudyConfigurationForm(SignOffMixin, forms.ModelForm):
    """Frontend Form for Study Configurations"""
    class Meta(object):
        model = StudyConfiguration
        widgets = {
            'name': forms.Textarea(attrs={'cols': 50, 'rows': 1}),
            'media_composition': forms.Textarea(attrs={'cols': 50, 'rows': 3}),
            'hardware_description': forms.Textarea(attrs={'cols': 50, 'rows': 3}),
        }
        exclude = ('',)


# Forms for plates may become more useful later
class AssayLayoutForm(SignOffMixin, forms.ModelForm):
    """Frontend Form for Assay Layouts

    Additional fields (not part of model):
    compound -- dropdown for selecting compounds to add to the Layout map
    concunit -- dropdown for selecting a concentration unit for the Layout map
    """
    def __init__(self, groups, *args, **kwargs):
        super(AssayLayoutForm, self).__init__(*args, **kwargs)
        self.fields['group'].queryset = groups
        self.fields['device'].queryset = Microdevice.objects.filter(
            device_type='plate'
        )

    compound = forms.ModelChoiceField(queryset=Compound.objects.all().order_by('name'), required=False)
    # Notice the special exception for %
    concunit = forms.ModelChoiceField(
        queryset=(PhysicalUnits.objects.filter(
            unit_type__unit_type='Concentration'
        ).order_by(
            'base_unit',
            'scale_factor'
        ) | PhysicalUnits.objects.filter(unit='%')),
        required=False, initial=4
    )

    class Meta(object):
        model = AssayLayout
        widgets = {
            'layout_name': forms.TextInput(attrs={'size': 35}),
        }
        exclude = tracking + restricted


class AssayPlateSetupForm(SignOffMixin, CloneableForm):
    """Frontend Form for Plate Setups"""
    def __init__(self, *args, **kwargs):
        """Init Plate Setup Form

        Orders AssayLayouts such that standard layouts appear first (does not currently filter)
        """
        super(AssayPlateSetupForm, self).__init__(*args, **kwargs)
        # Should the queryset be restricted by group?
        self.fields['assay_layout'].queryset = AssayLayout.objects.all().order_by('-standard', 'layout_name')

    class Meta(object):
        model = AssayPlateSetup
        widgets = {
            'notebook_page': forms.NumberInput(attrs={'style': 'width:50px;'}),
            'notes': forms.Textarea(attrs={'cols': 50, 'rows': 3}),
        }
        exclude = ('assay_run_id', 'group') + tracking + restricted

    def clean(self):
        """Clean Plate Setup Form

        Ensures that the given ID is unique for the current study
        Prevents changes to the setup if there is data uploaded
        """

        super(forms.ModelForm, self).clean()

        # Make sure the barcode/id is unique in the study
        if AssayPlateSetup.objects.filter(
                assay_run_id=self.instance.assay_run_id,
                assay_plate_id=self.cleaned_data.get('assay_plate_id')
        ).exclude(id=self.instance.id):
            raise forms.ValidationError({'assay_plate_id': ['ID/Barcode must be unique within study.']})

        # Check to see if data has been uploaded for this setup
        # Prevent changing the assay layout if this is the case
        # Prevent changing plate id if this is the case
        # Get readouts
        readout = AssayPlateReadout.objects.filter(setup=self.instance)
        if readout:
            if AssayReadout.objects.filter(
                    assay_device_readout=readout
            ) and self.cleaned_data.get('assay_layout') != self.instance.assay_layout:
                raise forms.ValidationError(
                    {'assay_layout': ['Assay layout cannot be changed after data has been uploaded.']}
                )
            # RENAMING PLATES WITH DATA IS NOW ALLOWED
            # if AssayReadout.objects.filter(
            #         assay_device_readout=readout
            # ) and self.cleaned_data.get('assay_plate_id') != self.instance.assay_plate_id:
            #     raise forms.ValidationError(
            #         {'assay_plate_id': ['Plate ID/Barcode cannot be changed after data has been uploaded.']}
            #     )


class AssayPlateCellsInlineFormset(CloneableBaseInlineFormSet):
    """Frontend Inline Formset for Plate Cells"""
    class Meta(object):
        model = AssayPlateCells
        exclude = ('',)


class AssayPlateReadoutForm(SignOffMixin, CloneableForm):
    """Frontend Form for Assay Plate Readouts"""
    def __init__(self, study, current, *args, **kwargs):
        """Init Assay Plate Readout Form

        Parameters:
        study -- the current study (for filtering Setups)
        current -- the current setup (if the Readout is being updated)

        Additional fields (not part of model):
        upload_type -- specifies whether the upload is in tabular or block format

        Filters units to be only time units
        Filters Setups to exclude Setups used by other Readouts
        """
        super(AssayPlateReadoutForm, self).__init__(*args, **kwargs)
        self.fields['timeunit'].queryset = PhysicalUnits.objects.filter(
            unit_type__unit_type='Time'
        ).order_by('scale_factor')
        exclude_list = AssayPlateReadout.objects.filter(setup__isnull=False).values_list('setup', flat=True)
        setups = AssayPlateSetup.objects.filter(assay_run_id=study).prefetch_related(
            'assay_run_id', 'assay_layout',
            'created_by').exclude(id__in=list(set(exclude_list)))
        if current:
            setups = setups | AssayPlateSetup.objects.filter(pk=current)
        self.fields['setup'].queryset = setups

    # upload_type = forms.ChoiceField(choices=(('Block', 'Block'), ('Tabular', 'Tabular')))

    overwrite_option = OVERWRITE_OPTIONS

    class Meta(object):
        model = AssayPlateReadout
        widgets = {
            'notebook_page': forms.NumberInput(attrs={'style': 'width:50px;'}),
            'treatment_time_length': forms.NumberInput(attrs={'style': 'width:174px;'}),
            'notes': forms.Textarea(attrs={'cols': 50, 'rows': 3}),
        }
        exclude = group + tracking + restricted


class AssayPlateResultForm(SignOffMixin, forms.ModelForm):
    """Frontend Form for Plate Test Results"""
    def __init__(self, study, current, *args, **kwargs):
        """Init Plate Test Results Form

        Parameters:
        study -- the current study (for filtering Readouts)
        current -- the current Results (if the Results are being updated)

        Filters Readouts to exclude Readouts being used by other Test Results
        """
        super(AssayPlateResultForm, self).__init__(*args, **kwargs)
        exclude_list = AssayPlateTestResult.objects.filter(readout__isnull=False).values_list('readout', flat=True)
        readouts = AssayPlateReadout.objects.filter(setup__assay_run_id=study).exclude(id__in=list(set(exclude_list)))
        if current:
            readouts = readouts | AssayPlateReadout.objects.filter(pk=current)
        readouts = readouts.prefetch_related('setup')
        self.fields['readout'].queryset = readouts

    class Meta(object):
        model = AssayPlateTestResult
        widgets = {
            'summary': forms.Textarea(attrs={'cols': 75, 'rows': 3}),
        }
        exclude = group + tracking + restricted


class PlateTestResultInlineFormset(BaseInlineFormSet):
    """Frontend inline for Individual Plate Results"""
    def __init__(self, *args, **kwargs):
        """Init Plate Result Inline

        Filters units such that only 'test' units appear
        """
        super(PlateTestResultInlineFormset, self).__init__(*args, **kwargs)
        unit_queryset = PhysicalUnits.objects.filter(
            availability__contains='test'
        ).order_by('base_unit', 'scale_factor')
        for form in self.forms:
            form.fields['test_unit'].queryset = unit_queryset

    class Meta(object):
        model = AssayPlateResult
        exclude = ('',)

    def clean(self):
        """Clean Plate Results Inline

        Prevents submission with no Results
        """
        forms_data = [f for f in self.forms if f.cleaned_data and not f.cleaned_data.get('DELETE', False)]

        # Number of results
        results = 0
        for form in forms_data:
            try:
                if form.cleaned_data:
                    results += 1
            except AttributeError:
                pass
        if results < 1:
            raise forms.ValidationError('You must have at least one result.')


def label_to_number(label):
    """Returns a numeric index from an alphabetical index"""
    num = 0
    for char in label:
        if char in string.ascii_letters:
            num = num * 26 + (ord(char.upper()) - ord('A')) + 1
    return num


def process_readout_value(value):
    """Returns processed readout value and whether or not to mark it invalid"""

    # Try to parse as a float
    try:
        value = float(value)
        return {'value': value, 'quality': u''}

    except ValueError:
        # If not a float, take slice of all but first character and try again
        sliced_value = value[1:]

        try:
            sliced_value = float(sliced_value)
            return {'value': sliced_value, 'quality': 'X'}

        except ValueError:
            return None


def get_row_and_column(well_id, offset):
    """Takes a well ID in the form A1 and returns a row and column index as a tuple

    Params:
    well_id - the well ID as a string
    offset - offset to resulting row and column indexes (to start at zero, for instance)
    """
     # Split the well into alphabetical and numeric
    row_label, column_label = re.findall(r"[^\W\d_]+|\d+", well_id)

    # PLEASE NOTE THAT THE VALUES ARE OFFSET BY ONE (to begin with 0)
    # Convert row_label to a number
    row_label = label_to_number(row_label) - offset
    # Convert column label to an integer
    column_label = int(column_label) - offset

    return (row_label, column_label)


class AssayPlateReadoutInlineFormset(CloneableBaseInlineFormSet):
    """Frontend Inline for Assay Plate Readout Assays (APRA)"""

    # EVIL WAY TO GET PREVIEW DATA
    preview_data = forms.BooleanField(initial=False)

    def __init__(self, *args, **kwargs):
        """Init APRA inline

        Filters units so that only units marked 'readout' appear
        """
        super(AssayPlateReadoutInlineFormset, self).__init__(*args, **kwargs)
        unit_queryset = PhysicalUnits.objects.filter(
            availability__contains='readout'
        ).order_by('base_unit', 'scale_factor')
        for form in self.forms:
            form.fields['readout_unit'].queryset = unit_queryset

    def clean(self):
        """Clean APRA Inline

        Validate unique, existing PLATE READOUTS
        """
        if self.data.get('setup', ''):
            setup_pk = int(self.data.get('setup'))
        else:
            raise forms.ValidationError('Please choose a plate setup.')
        setup = AssayPlateSetup.objects.get(pk=setup_pk)
        setup_id = setup.assay_plate_id

        # TODO REVIEW
        # Get upload type
        # upload_type = self.data.get('upload_type')

        forms_data = [f for f in self.forms if f.cleaned_data and not f.cleaned_data.get('DELETE', False)]

        plate_details = get_plate_details(self)

        assays = plate_details.get(setup_id, {}).get('assays', {})
        features = plate_details.get(setup_id, {}).get('features', {})
        assay_feature_to_unit = plate_details.get(setup_id, {}).get('assay_feature_to_unit', {})

        # If there is already a file in the database and it is not being replaced or cleared
        # (check for clear is implicit)
        if self.instance.file and not forms_data[0].files:
            saved_data = AssayReadout.objects.filter(assay_device_readout=self.instance).prefetch_related('assay')

            for raw in saved_data:
                assay = raw.assay.assay_id.assay_name.upper()
                value_unit = raw.assay.readout_unit.unit
                feature = raw.assay.feature

                # Raise error when an assay does not exist
                if assay not in assays:
                    raise forms.ValidationError(
                        'You can not remove the assay "{}" because it is in your uploaded data.'.format(assay))
                # Raise error if feature does not correspond?
                elif feature not in features:
                    raise forms.ValidationError(
                        'You can not remove the feature "{}" because it is in your uploaded data.'.format(feature))
                elif (assay, feature) not in assay_feature_to_unit:
                    raise forms.ValidationError(
                        'You can not change the assay-feature pair "{0}-{1}" '
                        'because it is in your uploaded data'.format(assay, feature)
                    )
                # Raise error if value_unit not equal to one listed in APRA
                # Note use of features to unit (unlike chips)
                if value_unit != assay_feature_to_unit.get((assay, feature), ''):
                    raise forms.ValidationError(
                        'The current value unit "%s" does not correspond with the readout unit of "%s"'
                        % (value_unit, assay_feature_to_unit.get((assay, feature), ''))
                    )

        # TODO what shall a uniqueness check look like?
        # If there is a new file
        if forms_data[0].files:
            test_file = forms_data[0].files.get('file', '')
            file_data = validate_file(
                self,
                test_file,
                'Plate',
                plate_details=plate_details,
                # upload_type=upload_type,
                study=setup.assay_run_id
            )
            # Evil attempt to acquire preview data
            self.forms[0].cleaned_data['preview_data'] = file_data

        return self.forms


class AssayChipReadoutInlineFormset(CloneableBaseInlineFormSet):
    """Frontend Inline for Chip Readout Assays (ACRA)"""

    # EVIL WAY TO GET PREVIEW DATA
    preview_data = forms.BooleanField(initial=False)

    def __init__(self, *args, **kwargs):
        """Init ACRA Inline

        Filters units so that only units marked 'readout' appear
        """
        super(AssayChipReadoutInlineFormset, self).__init__(*args, **kwargs)
        unit_queryset = PhysicalUnits.objects.filter(
            availability__contains='readout'
        ).order_by('base_unit', 'scale_factor')
        for form in self.forms:
            form.fields['readout_unit'].queryset = unit_queryset

    def clean(self):
        """Validate unique, existing Chip Readout IDs"""
        if self.data.get('chip_setup', ''):
            setup_pk = int(self.data.get('chip_setup'))
        else:
            raise forms.ValidationError('Please choose a chip setup.')
        setup = AssayChipSetup.objects.get(pk=setup_pk)
        setup_id = setup.assay_chip_id

        # Throw error if headers is not valid
        try:
            headers = int(self.data.get('headers', '')) if self.data.get('headers', '') else 0
        except:
            raise forms.ValidationError('Please make number of headers a valid number.')

        forms_data = [f for f in self.forms if f.cleaned_data and not f.cleaned_data.get('DELETE', False)]

        chip_details = get_chip_details(self)

        assays = chip_details.get(setup_id, {}).get('assays', {})

        # If there is already a file in the database and it is not being replaced or cleared
        #  (check for clear is implicit)
        if self.instance.file and not forms_data[0].files:
            new_time_unit = self.instance.timeunit
            old_time_unit = AssayChipReadout.objects.get(id=self.instance.id).timeunit

            # Fail if time unit does not match
            if new_time_unit != old_time_unit:
                raise forms.ValidationError(
                    'The time unit "%s" does not correspond with the selected readout time unit of "%s"'
                    % (new_time_unit, old_time_unit))

            saved_data = AssayChipRawData.objects.filter(assay_chip_id=self.instance).prefetch_related(
                'assay_id__assay_id'
            )

            for raw in saved_data:

                assay = raw.assay_id.assay_id.assay_name.upper()
                value_unit = raw.assay_id.readout_unit.unit

                # Raise error when an assay does not exist
                if assay not in assays:
                    raise forms.ValidationError(
                        'You can not remove the assay "%s" because it is in your uploaded data.' % assay)
                # Raise error if value_unit not equal to one listed in ACRA
                elif value_unit != assays.get(assay, ''):
                    raise forms.ValidationError(
                        'The current value unit "%s" does not correspond with the readout unit of "%s"'
                        % (value_unit, assays.get(assay, ''))
                    )

        # If there is a new file
        if forms_data[0].files:
            test_file = forms_data[0].files.get('file', '')
            file_data = validate_file(
                self,
                test_file,
                'Chip',
                headers=headers,
                chip_details=chip_details,
                plate_details=None,
                study=setup.assay_run_id
            )
            # Evil attempt to acquire preview data
            self.forms[0].cleaned_data['preview_data'] = file_data

        return self.forms


# Now uses unicode instead of string
def stringify_excel_value(value):
    """Given an excel value, return a unicode cast of it

    This also converts floats to integers when possible
    """
    # If the value is just a string literal, return it
    if type(value) == str or type(value) == unicode:
        return unicode(value)
    else:
        try:
            # If the value can be an integer, make it into one
            if int(value) == float(value):
                return unicode(int(value))
            else:
                return unicode(float(value))
        except:
            return unicode(value)


# SPAGHETTI CODE FIND A BETTER PLACE TO PUT THIS?
def valid_chip_row(row):
    """Confirm that a row is valid"""
    return row and all(row[:5] + [row[6]])


def get_bulk_datalist(sheet):
    """Get a list of lists where each list is a row and each entry is a value"""
    # Get datalist
    datalist = []

    # Include the first row (the header)
    for row_index in range(sheet.nrows):
        datalist.append([stringify_excel_value(value) for value in sheet.row_values(row_index)])

    return datalist


# TODO FIX ORDER OF ARGUMENTS
def get_sheet_type(header, sheet_name=''):
    """Get the sheet type from a given header (chip, tabular, block, or unknown)

    Param:
    header - the header in question
    sheet_name - the sheet name for reporting errors (default empty string)
    """
    # From the header we need to discern the type of upload
    # Check if chip
    if 'CHIP' in header[0].upper() and 'ASSAY' in header[3].upper():
        sheet_type = 'Chip'

    # Check if plate tabular
    elif 'PLATE' in header[0].upper() and 'WELL' in header[1].upper() and 'ASSAY' in header[2].upper()\
            and 'FEATURE' in header[3].upper() and 'UNIT' in header[4].upper():
        sheet_type = 'Tabular'

    # Check if plate block
    elif 'PLATE' in header[0].upper() and 'ASSAY' in header[2].upper() and 'FEATURE' in header[4].upper()\
            and 'UNIT' in header[6].upper():
        sheet_type = 'Block'

    # Throw error if can not be determined
    else:
        # For if we decide not to throw errors
        sheet_type = 'Unknown'
        raise forms.ValidationError(
            'The header of sheet "{0}" was not recognized.'.format(sheet_name)
        )

    return sheet_type


class ReadoutBulkUploadForm(forms.ModelForm):
    """Form for Bulk Uploads"""
    bulk_file = forms.FileField()

    overwrite_option = OVERWRITE_OPTIONS

    class Meta(object):
        model = AssayRun
        fields = ('bulk_file',)

    def clean_bulk_file(self):
        data = super(ReadoutBulkUploadForm, self).clean()

        # Get the study in question
        study = self.instance

        test_file = data.get('bulk_file', '')

        if not test_file:
            raise forms.ValidationError('No file was supplied.')

        # For the moment, just have headers be equal to one?
        headers = 1

        file_data = validate_file(
            self,
            test_file,
            'Bulk',
            headers=headers,
            study=study
        )

        return file_data
