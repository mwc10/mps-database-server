# coding=utf-8

import ujson as json
import os
import hashlib
import csv

from pandas import *
from django.db import connection

from mps.settings import MEDIA_ROOT

import scipy.spatial
import scipy.cluster
import numpy as np

from compounds.models import Compound
from .models import Bioactivity, PubChemBioactivity, Assay
from drugtrials.models import FindingResult

from django.core import serializers
# TODO FIX TARGET VS. ASSAY ORGANISM CONFLICT


def generate_record_frequency_data(query):
    result = {}

    for q in query:
        # TODO CRUDE; REQUIRES REVISION
        if type(q) == tuple:
            element = '|'.join([unicode(item) for item in q])
        else:
            element = ''.join(q)
        if element:
            if element in result:
                frequency = result.get(element)
                frequency += 1
                result.update({element: frequency})
            else:
                result.update({element: 1})

    result_list = []

    for key, value in result.iteritems():
        result_list.append([key, value])

    return result_list


def generate_list_of_all_data_in_bioactivities(pubchem, organisms, targets):
    bioactivities_data = generate_list_of_all_bioactivities_in_bioactivities(pubchem)
    compounds_data = generate_list_of_all_compounds_in_bioactivities(pubchem)
    # Targets are based on assay and not dependent on pubchem
    targets_data = generate_list_of_all_targets_in_bioactivities(pubchem, organisms, targets)
    drugtrial_data = generate_list_of_all_drugtrials(organisms)

    result = {
        'bioactivities': bioactivities_data,
        'compounds': compounds_data,
        'targets': targets_data,
        'drugtrials': drugtrial_data
    }

    return result


def generate_list_of_all_bioactivities_in_bioactivities(pubchem):
    if pubchem:
        pubchem_bioactivities = PubChemBioactivity.objects.all().values_list('activity_name')
        result = generate_record_frequency_data(pubchem_bioactivities)
    else:
        chembl_bioactivities = Bioactivity.objects.all().values_list('standard_name')
        result = generate_record_frequency_data(chembl_bioactivities)
    return result


def generate_list_of_all_targets_in_bioactivities(pubchem, organisms, targets):
    # Requires revision
    if pubchem:
        initial_targets = PubChemBioactivity.objects.filter(
            assay__target__organism__in=organisms,
            assay__target__target_type__in=targets
        )

        no_null_targets = PubChemBioactivity.objects.filter(assay__target__isnull=False)

        if '!No Organism' in organisms:
            all_targets = initial_targets | no_null_targets.filter(
                assay__target__organism='') | no_null_targets.filter(assay__target__organism="Unspecified")
        else:
            all_targets = initial_targets

        all_targets = all_targets.select_related('assay__target').values_list('assay__target__name')

        result = generate_record_frequency_data(all_targets)

    else:
        initial_targets = Bioactivity.objects.filter(
            target__organism__in=organisms,
            target__target_type__in=targets
        )

        no_null_targets = Bioactivity.objects.filter(target__isnull=False)

        if '!No Organism' in organisms:
            all_targets = initial_targets | no_null_targets.filter(
                target__organism='') | no_null_targets.filter(target__organism="Unspecified")
        else:
            all_targets = initial_targets

        all_targets = all_targets.prefetch_related('target').values_list('target__name')

        result = generate_record_frequency_data(all_targets)

    # Add no target
    result.append(['!No Target', 999999999])

    return result


# Worry about filtering by organism later
# FK for organism is a little odd right now
def generate_list_of_all_drugtrials(desired_organisms):
    # TODO
    # This requires refactoring, magic conversion tables are not good practice
    organisms = {
        'Homo sapiens': 'Human',
        'Rattus norvegicus': 'Rat',
        'Canis lupus familiaris': 'Dog'
    }

    desired_organisms = [organisms.get(organism, '') for organism in desired_organisms]

    result = FindingResult.objects.filter(
        value__isnull=False, drug_trial__species__species_name__in=desired_organisms
    ).select_related('drug_trial__species', 'finding_name').values_list('finding_name__finding_name', flat=True)

    result = generate_record_frequency_data(result)

    return result


def generate_list_of_all_compounds_in_bioactivities(pubchem):
    if pubchem:
        pubchem_compounds = PubChemBioactivity.objects.all().prefetch_related(
            'compound'
        ).values_list(
            'compound__name',
            'compound__known_drug',
            'compound__logp',
            'compound__molecular_weight'
        )
        result = generate_record_frequency_data(pubchem_compounds)
    else:
        chembl_compounds = Bioactivity.objects.all().prefetch_related(
            'compound'
        ).values_list(
            'compound__name',
            'compound__known_drug',
            'compound__logp',
            'compound__molecular_weight'
        )
        result = generate_record_frequency_data(chembl_compounds)

    return result


def get_form_data(request):
    # convert data sent in request to a dict data type from a string data type
    request_filter = json.loads(request.body)

    desired_targets = [
        x.get(
            'name'
        ) for x in request_filter.get(
            'targets_filter'
        ) if x.get(
            'is_selected'
        ) is True
    ]

    desired_compounds = [
        x.get(
            'name'
        ) for x in request_filter.get(
            'compounds_filter'
        ) if x.get(
            'is_selected'
        ) is True
    ]

    desired_bioactivities = [
        x.get(
            'name'
        ) for x in request_filter.get(
            'bioactivities_filter'
        ) if x.get(
            'is_selected'
        ) is True
    ]

    if 'drugtrials_filter' in request_filter:
        desired_drugtrials = [
            x.get(
                'name'
            ) for x in request_filter.get(
                'drugtrials_filter'
            ) if x.get(
                'is_selected'
            ) is True
        ]
    else:
        desired_drugtrials = []

    desired_organisms = [
        x.get(
            'name'
        ) for x in request_filter.get(
            'organisms_filter'
        ) if x.get(
            'is_selected'
        ) is True
    ]

    log_scale = request_filter.get('log_scale', False)
    normalized = request_filter.get('normalize_bioactivities', False)

    method = str(request_filter.get('method', ''))
    metric = str(request_filter.get('metric', ''))

    # Whether or not to use chemical properties
    chemical_properties = request_filter.get('chemical_properties', False)

    pubchem = request_filter.get('pubchem', True)

    return {
        'desired_targets': desired_targets,
        'desired_compounds': desired_compounds,
        'desired_bioactivities': desired_bioactivities,
        'desired_drugtrials': desired_drugtrials,
        'desired_organisms': desired_organisms,
        'log_scale': log_scale,
        'normalized': normalized,
        'method': method,
        'metric': metric,
        'chemical_properties': chemical_properties,
        'pubchem': pubchem
    }


def get_filtered_bioactivities(
        pubchem,
        desired_compounds,
        desired_targets,
        desired_bioactivities,
        desired_organisms
):
    # Filter based on bioactivity
    if pubchem:
        q = PubChemBioactivity.objects.filter(activity_name__in=desired_bioactivities)
    else:
        q = Bioactivity.objects.filter(standard_name__in=desired_bioactivities)

    # Filter based on compound
    q = q.filter(compound__name__in=desired_compounds)

    # TODO FILTER TARGETS WITH BIOACTIVITY WHEN CHEMBL

    # Filter based on target type
    #q_targets = q.filter(assay__target__target_type__in=desired_target_types)

    # Filter based on targets
    if pubchem:
        q_targets = q.filter(assay__target__name__in=desired_targets)

        if '!No Target' in desired_targets and '!No Organism' in desired_organisms:
            q = q_targets | q.filter(assay__target__isnull=True)

        else:
            q = q_targets

        q_non_null_targets = q_targets.filter(assay__target__isnull=False)

        # Filter based on organism
        q_organisms = q.filter(
            assay__organism__in=desired_organisms
        ) | q.filter(assay__target__organism__in=desired_organisms)

        # If no organism selected
        # TODO NEEDS REVISION
        if '!No Organism' in desired_organisms:
            q_organisms = q_organisms | q.filter(assay__target__isnull=True, assay__organism='')

            if q_non_null_targets:
                q = q_organisms | q_non_null_targets.filter(
                    assay__target__organism='Unspecified',
                    assay__organism=''
                ) | q_non_null_targets.filter(
                    assay__target__organism='',
                    assay__organism=''
                )
        else:
            q = q_organisms

        q = q.prefetch_related(
            'compound',
            'assay'
        ).select_related(
            'assay__target'
        )

    else:
        q_targets = q.filter(target__name__in=desired_targets)

        q_non_null_targets = q_targets.filter(target__isnull=False)

        if '!No Target' in desired_targets:
            q = q_targets | q.filter(target__isnull=True)

            if q_non_null_targets:
                q = q | q_non_null_targets.filter(
                    target__name='Unchecked'
                )
        else:
            q = q_targets

        # Filter based on organism
        q_organisms = q.filter(target__organism__in=desired_organisms)

        # If no organism selected
        # TODO NEEDS REVISION
        if '!No Organism' in desired_organisms:
            q_organisms = q_organisms | q.filter(target__isnull=True)

            if q_non_null_targets:
                q = q_organisms | q_non_null_targets.filter(
                    target__organism='Unspecified'
                ) | q_non_null_targets.filter(
                    target__organism=''
                )
        else:
            q = q_organisms

        q = q.prefetch_related(
            'compound',
            'assay',
            'target'
        )

    return q


# TODO STANDARD BIOACTIVITIES FOR ChEBML (right now just PubChem)
def fetch_all_standard_bioactivities_data(
        pubchem,
        desired_compounds,
        desired_targets,
        desired_bioactivities,
        desired_organisms,
        normalized,
        log_scale
):
    # First, we acquire all the filtered hits
    filtered_bioactivities = get_filtered_bioactivities(
        pubchem,
        desired_compounds,
        desired_targets,
        desired_bioactivities,
        desired_organisms
    )

    # Then we can iterate over them to acquire the average values and so on

    # This dictionary will take a tuple as a key (compound, target, bioactivity, organism)
    # DON'T WORRY ABOUT UNITS AS EVERYTHING IS IN uM
    bioactivities = {}

    # Collect every value
    for bio in filtered_bioactivities:
        compound = bio.compound.name

        if pubchem:
            if bio.assay.target:
                target = bio.assay.target.name
            else:
                target = 'No Target'

            activity = bio.activity_name

            if bio.assay.target and bio.assay.target.organism:
                organism = bio.assay.target.organism
            elif bio.assay.organism:
                organism = bio.assay.organism
            else:
                organism = 'No Organism'
        else:
            if bio.target:
                target = bio.target.name
            else:
                target = 'No Target'

            activity = bio.standard_name

            if bio.target and bio.target.organism:
                organism = bio.target.organism
            elif bio.assay.organism:
                organism = bio.assay.organism
            else:
                organism = 'No Organism'

        bio_key = (compound, target, activity, organism)

        if (normalized and bio.normalized_value) or (not normalized and bio.value):
            if normalized:
                value = bio.normalized_value
            else:
                value = bio.value
            if log_scale:
                value = np.log10(value)
            if bio_key not in bioactivities:
                bioactivities[bio_key] = [value]
            else:
                bioactivities[bio_key].append(value)

    results = []

    # Mean every list of values and build the dictionary of values to return
    for bio_key in bioactivities:
        bio_to_add = {}
        bio_to_add['value'] = sum(bioactivities[bio_key])/float(len(bioactivities[bio_key]))
        bio_to_add['compound'] = bio_key[0]
        bio_to_add['target'] = bio_key[1] + '_' + bio_key[3]
        bio_to_add['bioactivity'] = bio_key[2]
        results.append(bio_to_add)

    return results


# TODO FIX NULL TARGETS AND NULL ORGANISMS
def fetch_all_standard_drugtrials_data(
        desired_compounds,
        desired_drugtrials,
        desired_organisms,
        normalized,
        log_scale
):
    # TODO
    # This requires refactoring, magic conversion tables are not good practice
    organisms = {
        'Homo sapiens': 'Human',
        'Rattus norvegicus': 'Rat',
        'Canis lupus familiaris': 'Dog'
    }

    desired_organisms = [organisms.get(organism,'') for organism in desired_organisms]

    # TODO: FIXME
    # Nonstandard values?
    # Please note that normalization now goes from 0.0001 to 1

    results = []

    for finding in desired_drugtrials:

        drugtrial_data = FindingResult.objects.filter(
            finding_name__finding_name=finding,
            value__isnull=False,
            drug_trial__compound__name__in=desired_compounds,
            drug_trial__species__species_name__in=desired_organisms
        )
        #average = 0
        min = 999999999
        max = -999999999

        for result in drugtrial_data:
            value = result.value
            #average += value
            if value < min:
                min = value
            if value > max:
                max = value

        #average = average / len(drugtrial_data)

        for result in drugtrial_data:
            compound = result.drug_trial.compound.name

            findingresult = result.finding_name.finding_name

            value = result.value

            if normalized:
                try:
                    value = (0.9999)*((value-min)/(max-min)) + 0.0001
                except:
                    value = 1

            # Please note that negative and zero values ARE EXCLUDED
            if log_scale:
                if value <= 0:
                    continue

                value = np.log10(value)

            results.append(
                {
                    'compound': compound,
                    # Testing for now (contrived name)
                    'target_bioactivity_pair': findingresult,
                    'value': value
                }
            )

    return results


def fetch_all_standard_mps_assay_data():
    # using values for now, FUTURE: use standardized_values
    cursor = connection.cursor()

    # TODO: FIXME
    cursor.execute(
        ''
    )

    # bioactivity is a tuple:
    # (compound name, target name, the bioactivity, value)
    # (0            , 1          , 2              , 3    )
    query = cursor.fetchall()

    result = []

    for q in query:
        result.append(
            {
                'compound': q[0],
                'target': q[1],
                'bioactivity': q[2],
                'value': q[3]
            }
        )

    cursor.close()

    return result

import collections


# dic is a dictionary capable of autovivification
def dic():
    return collections.defaultdict(dic)


def heatmap(request):
    if len(request.body) == 0:
        return {'error': 'empty request body'}

    form = get_form_data(request)

    desired_compounds = form['desired_compounds']
    desired_bioactivities = form['desired_bioactivities']
    desired_targets = form['desired_targets']
    desired_drugtrials = form['desired_drugtrials']
    desired_organisms = form['desired_organisms']
    normalized = form['normalized']
    log_scale = form['log_scale']
    method = form['method']
    metric = form['metric']

    pubchem = form['pubchem']

    # throw error if no compounds are selected
    if not desired_compounds:
        return {'error': 'Select at least one compound.'}

    # throw error if no drugtrials or no pairs are chosen
    if not desired_bioactivities and not desired_targets and not desired_drugtrials:
        return {'error': 'Select at least one target and at least one bioactivity or at least one drugtrial.'}

    all_std_bioactivities = fetch_all_standard_bioactivities_data(
        pubchem,
        desired_compounds,
        desired_targets,
        desired_bioactivities,
        desired_organisms,
        normalized,
        log_scale
    )

    all_std_drugtrial = fetch_all_standard_drugtrials_data(
        desired_compounds,
        desired_drugtrials,
        desired_organisms,
        normalized,
        log_scale
    )

    if not all_std_bioactivities and not all_std_drugtrial:
        return {'error': 'no standard bioactivities or drugtrial data'}

    if all_std_bioactivities:
        bioactivities_data = pandas.DataFrame(
            all_std_bioactivities,
            columns=['compound', 'target', 'bioactivity', 'value']
        ).fillna(0)

        pivoted_data = pandas.pivot_table(
            bioactivities_data,
            values='value',
            columns=['target', 'bioactivity'],
            index='compound'
        )

        unwound_data = pivoted_data.unstack().reset_index(name='value').dropna()

        unwound_data['target_bioactivity_pair'] = \
            unwound_data['target'] + '_' + unwound_data['bioactivity']

        del unwound_data['target']
        del unwound_data['bioactivity']

        data_order = ['compound', 'target_bioactivity_pair', 'value']
        rearranged_data = unwound_data[data_order]

    else:
        rearranged_data = pandas.DataFrame()

    if all_std_drugtrial:
        drugtrial_df = pandas.DataFrame(all_std_drugtrial, columns=['compound', 'target_bioactivity_pair', 'value'])

        rearranged_data = rearranged_data.append(drugtrial_df)

    # try to make heatmap folder and ignore the exception if the folder exists
    try:
        os.makedirs(os.path.join(MEDIA_ROOT, 'heatmap'))
    except OSError:
        pass

    # generate a unique full path for data and rows and columns information

    data_hash = hashlib.sha512(
        str(rearranged_data)
    ).hexdigest()[:10]

    fullpath_without_extension = os.path.join(
        MEDIA_ROOT,
        'heatmap',
        data_hash
    )

    # string representation of the respective full paths
    data_csv_fullpath = fullpath_without_extension + '_data.csv'

    # generate file handles for the csv writer
    data_csv_filehandle = open(data_csv_fullpath, "w")

    # generate csv writers for each file handle
    data_csv_writer = csv.writer(data_csv_filehandle)

    # write out our data lists into csv format
    data_csv_writer.writerow(['compound', 'bioactivity', 'value'])
    data_csv_writer.writerows(rearranged_data.values.tolist())

    # close the csv files that we have written so far
    data_csv_filehandle.close()

    heatmap_url_prefix = '/media/heatmap/'

    data_csv_relpath = heatmap_url_prefix + os.path.basename(
        data_csv_fullpath
    )

    # Make rearranged values into a list for cluster
    rearranged_data = rearranged_data.values.tolist()

    # Initially all compounds are valid
    valid_compounds = list(desired_compounds)
    data = {'compounds': valid_compounds}

    # List of all unique bioactivities
    bioactivities = {}

    if all_std_bioactivities or all_std_drugtrial:

        # Initial dictionary before final data
        initial_dic = dic()
        # use desired_compounds to reference compounds

        # Go through every entry and put the data in the initial_dic and bioactivities
        for line in rearranged_data:
            compound = line[0]
            bioactivity = line[1]
            value = line[2]
            initial_dic[compound][bioactivity] = value
            if bioactivity not in bioactivities:
                bioactivities[bioactivity] = True

        # Fill in missing data with None
        for bioactivity in bioactivities:
            for compound in initial_dic:
                if not bioactivity in initial_dic[compound]:
                    initial_dic[compound][bioactivity] = None

        # Only grab valid compounds (TEST)
        valid_compounds = [compound for compound in desired_compounds if compound in initial_dic]

        # Rearrange for final data
        data['compounds'] = valid_compounds

        # Update the values for each bioactivity
        for bioactivity in bioactivities:
            values = []
            for compound in valid_compounds:
                values.append(initial_dic[compound][bioactivity])
            # Get median from list after excluding all None values
            median = np.median(np.array([value for value in values if value != None]))
            maximum = max(values)

            # Avoid anomalies by arbitrarily putting median to 10% when max == median
            if median == maximum:
                median = median * 0.1
            # Convert values such that there are no None values
            values = [value if value != None else median for value in values]
            data.update({bioactivity:values})

    df = pandas.DataFrame(data)

    # For *Rows*

    # Determine distances (default is Euclidean)
    # The data frame should encompass all of the bioactivities and drugtrials
    frame = [bioactivity for bioactivity in bioactivities]
    dataMatrix = np.array(df[frame])
    distMat = scipy.spatial.distance.pdist(dataMatrix, metric=metric)
    # GOTCHA
    # Small numbers appear to trigger a quirk in Scipy (removing them most expedient solution)
    distMat[abs(distMat)<1e-10] = 0.0
    # Large numbers also appear to be problematic

    row_leaves = valid_compounds
    col_leaves = frame

    # Cluster hierarchicaly using scipy
    if distMat.any():
        clusters = scipy.cluster.hierarchy.linkage(distMat, method=method)
        dendro = scipy.cluster.hierarchy.dendrogram(clusters, orientation='right', no_plot=True)
        row_leaves = [valid_compounds[i] for i in dendro['leaves']]

    # For *Columns*

    distMat = scipy.spatial.distance.pdist(dataMatrix.T, metric=metric)
    distMat[abs(distMat)<1e-10] = 0.0

    if distMat.any():
        clusters = scipy.cluster.hierarchy.linkage(distMat, method=method)
        dendro = scipy.cluster.hierarchy.dendrogram(clusters, orientation='right', no_plot=True)
        col_leaves = [frame[i] for i in dendro['leaves']]

    # return the paths to each respective filetype as a JSON
    return {
        # csv filepath for the data
        'data_csv': data_csv_relpath,
        'row_order': row_leaves,
        'col_order': col_leaves,
    }


def cluster(request):
    if len(request.body) == 0:
        return {'error': 'empty request body'}

    form = get_form_data(request)

    desired_compounds = form['desired_compounds']
    desired_bioactivities = form['desired_bioactivities']
    desired_targets = form['desired_targets']
    desired_drugtrials = form['desired_drugtrials']
    desired_organisms = form['desired_organisms']
    normalized = form['normalized']
    log_scale = form['log_scale']
    chemical_properties = form['chemical_properties']
    method = form['method']
    metric = form['metric']

    pubchem = form['pubchem']

    # throw error if only one compound is selected (can not cluster just one)
    if len(desired_compounds) < 2:
        return {'error': 'require more than one compound to cluster'}

    # throw error if no drugtrials or no pairs are chosen and chemical properties is not checked
    if (not desired_bioactivities or not desired_targets) and not desired_drugtrials and not chemical_properties:
        return {'error': 'Select at least one target and at least one bioactivity or at least one drugtrial.'}

    all_std_bioactivities = fetch_all_standard_bioactivities_data(
        pubchem,
        desired_compounds,
        desired_targets,
        desired_bioactivities,
        desired_organisms,
        normalized,
        log_scale
    )

    all_std_drugtrial = fetch_all_standard_drugtrials_data(
        desired_compounds,
        desired_drugtrials,
        desired_organisms,
        normalized,
        log_scale
    )

    # Should throw error only if no chemical_properties and no bioactivities
    if not all_std_drugtrial and not all_std_bioactivities and not chemical_properties:
        return {'error': 'no standard bioactivities'}

    # Initially all compounds are valid
    valid_compounds = list(desired_compounds)
    data = {'compounds': valid_compounds}

    # List of all unique bioactivities
    bioactivities = {}

    if all_std_bioactivities or all_std_drugtrial:

        if all_std_bioactivities:
            bioactivities_data = pandas.DataFrame(
                all_std_bioactivities,
                columns=['compound', 'target', 'bioactivity', 'value']
            ).fillna(0)

            pivoted_data = pandas.pivot_table(
                bioactivities_data,
                values='value',
                columns=['target', 'bioactivity'],
                index='compound'
            )

            unwound_data = pivoted_data.unstack().reset_index(name='value').dropna()

            unwound_data['target_bioactivity_pair'] = \
                unwound_data['target'] + '_ ' + unwound_data['bioactivity']

            del unwound_data['target']
            del unwound_data['bioactivity']

            data_order = ['compound', 'target_bioactivity_pair', 'value']
            rearranged_data = unwound_data[data_order]

        else:
            rearranged_data = pandas.DataFrame()

        if all_std_drugtrial:
            drugtrial_df = pandas.DataFrame(
                all_std_drugtrial,
                columns=['compound', 'target_bioactivity_pair', 'value']
            )

            rearranged_data = rearranged_data.append(drugtrial_df)

        rearranged_data = rearranged_data.values.tolist()

        # Initial dictionary before final data
        initial_dic = dic()
        # use desired_compounds to reference compounds

        # Go through every entry and put the data in the initial_dic and bioactivities
        for line in rearranged_data:
            compound = line[0]
            bioactivity = line[1]
            value = line[2]
            initial_dic[compound][bioactivity] = value
            if bioactivity not in bioactivities:
                bioactivities[bioactivity] = True

        # Only grab valid compounds (TEST)
        if not chemical_properties:
            valid_compounds = [compound for compound in desired_compounds if compound in initial_dic]
        else:
            valid_compounds = desired_compounds

        # Fill in missing data with zeroes
        for bioactivity in bioactivities:
            for compound in valid_compounds:
                # For when absolutely no drugtrial or bioactivity data exists for the compound
                if not compound in initial_dic:
                    initial_dic[compound][bioactivity] = None
                if not bioactivity in initial_dic[compound]:
                    initial_dic[compound][bioactivity] = None

        # Rearrange for final data
        data['compounds'] = valid_compounds

        # Update the values for each bioactivity
        for bioactivity in bioactivities:
            values = []
            for compound in valid_compounds:
                values.append(initial_dic[compound][bioactivity])
            # Get median from list after excluding all None values
            median = np.median(np.array([value for value in values if value != None]))
            maximum = max(values)

            # Avoid anomalies by arbitrarily putting median to 10% when max == median
            if median == maximum:
                median = median * 0.1
            # Convert values such that there are no None values
            values = [value if value != None else median for value in values]
            data.update({bioactivity:values})

    # List of properties
    props = ['molecular_weight',
             'rotatable_bonds',
             'acidic_pka',
             'basic_pka',
             'logp',
             'logd',
             'alogp',
             'ro5_violations',
             'ro3_passes']

    # list of dics of compounds (creating this prevents excessive calls to the database
    compound_data = Compound.objects.filter(name__in=valid_compounds).values()

    # Update values for chemical properties (if chemical_properties)
    if chemical_properties:
        for prop in props:
            values = []
            for compound in compound_data:
                # Get data for prop here
                # This is a rather inefficient means of acquiring data
                values.append(compound.get(prop,None))
            # Get median from list after excluding all None values
            median = np.median(np.array([value for value in values if value != None]))
            maximum = max(values)

            # Avoid anomalies by arbitrarily putting median to 10% when max == median
            if median == maximum:
                median = median * 0.1

            # Convert values such that there are no None values
            values = [value if value != None else median for value in values]
            data.update({prop:values})

    df = pandas.DataFrame(data)

    # Determine distances (default is Euclidean)
    # The data frame should encompass all of the bioactivities
    frame = [bioactivity for bioactivity in bioactivities]
    if chemical_properties:
        frame.extend(props)
    dataMatrix = np.array(df[frame])
    distMat = scipy.spatial.distance.pdist(dataMatrix, metric=metric)
    # GOTCHA
    # Small numbers appear to trigger a quirk in Scipy (removing them most expedient solution)
    distMat[abs(distMat)<1e-10] = 0.0

    # Cluster hierarchicaly using scipy
    clusters = scipy.cluster.hierarchy.linkage(distMat, method=method)
    T = scipy.cluster.hierarchy.to_tree(clusters, rd=False)

    # Create dictionary for labeling nodes by their IDs
    labels = list(df['compounds'])
    id2name = dict(zip(range(len(labels)), labels))

    # Create a nested dictionary from the ClusterNode's returned by SciPy
    def add_node(node, parent):
        # First create the new node and append it to its parent's children
        newNode = dict(node_id=node.id, children=[])
        parent["children"].append(newNode)

        # Recursively add the current node's children
        if node.left: add_node(node.left, newNode)
        if node.right: add_node(node.right, newNode)

    # Initialize nested dictionary for d3, then recursively iterate through tree
    d3Dendro = dict(children=[], name="Root")
    add_node(T, d3Dendro)

    # Label each node with the names of each leaf in its subtree
    def label_tree(n):
        # If the node is a leaf, then we have its name
        if len(n["children"]) == 0:
            leafNames = [id2name[n["node_id"]]]

        # If not, flatten all the leaves in the node's subtree
        else:
            leafNames = reduce(lambda ls, c: ls + label_tree(c), n["children"], [])

        # Delete the node id since we don't need it anymore and
        # it makes for cleaner JSON
        del n["node_id"]

        # Labeling convention: new-line separated leaf names
        n["name"] = name = "\n".join(sorted(map(str, leafNames)))

        return leafNames


    label_tree(d3Dendro["children"][0])

    # Turn bioactivities into a sorted list of bioactivity-target pairs
    bioactivities = sorted(bioactivities.keys())

    compounds = {}

    for compound in compound_data:
        CHEMBL = compound.get('chemblid')
        name = compound.get('name')
        known_drug = compound.get('known_drug')
        ro3 = compound.get('ro3_passes')
        ro5 = compound.get('ro5_violations')
        species = compound.get('species')
        data ={
            'CHEMBL': CHEMBL,
            'name': name,
            'knownDrug': known_drug,
            'ro3': ro3,
            'ro5': ro5,
            'species': species,
        }

        compounds[name] = data

    return {
        # json data
        'data_json': d3Dendro,
        'bioactivities': bioactivities,
        'compounds': compounds
    }

    # fullpath = os.path.join(
    #     MEDIA_ROOT,
    #     'heatmap',
    #     "d3-dendrogram.json"
    # )
    #
    # # Output to JSON
    # json.dump(d3Dendro, open(fullpath, "w"), sort_keys=True, indent=4)
    #
    # cluster_url_prefix = '/media/cluster/'
    #
    # data_json_relpath = cluster_url_prefix + "d3-dendrogram.json"
    #
    # # return the paths to each respective filetype as a JSON
    # return {
    #     # json filepath for the data
    #     'data_json': data_json_relpath
    # }


def table(request):
    if len(request.body) == 0:
        return {'error': 'empty request body'}

    form = get_form_data(request)

    desired_compounds = form['desired_compounds']
    desired_bioactivities = form['desired_bioactivities']
    desired_targets = form['desired_targets']
    desired_organisms = form['desired_organisms']
    pubchem = form['pubchem']

    # throw error if no compounds are selected
    if len(desired_compounds) < 1:
        return {'error': 'Select at least one compound.'}

    # throw error if no targets are selected
    if len(desired_targets) < 1:
        return {'error': 'Select at least one target.'}

    # throw error if no bioactivities are selected
    if len(desired_bioactivities) < 1:
        return {'error': 'Select at least one bioactivity.'}

    # throw error for very large queries
    #if 'Rattus norvegicus' in desired_targets and len(desired_compounds) >= 15:
    #   return {'error': 'Many bioactivities are listed with Rattus norvegicus as a target, either deselect it or choose fewer than 15 compounds.'}

    q = get_filtered_bioactivities(
        pubchem,
        desired_compounds,
        desired_targets,
        desired_bioactivities,
        desired_organisms
    )

    length = q.count()

    # Prefetch all foreign keys
    q = q.select_related(
        'compound',
        'assay__target',
        'assay'
    )[:5000]

    data = []

    for bioactivity in q:

        id = bioactivity.pk
        compound = bioactivity.compound.name
        compoundid = bioactivity.compound.id

        if pubchem:
            if bioactivity.assay.target:
                target = bioactivity.assay.target.name
                organism = bioactivity.assay.target.organism
            else:
                target = u''
                organism = bioactivity.assay.organism
        else:
            if bioactivity.target:
                target = bioactivity.target.name
                organism = bioactivity.target.organism
            else:
                target = u''
                organism = bioactivity.assay.organism

        chemblid = bioactivity.assay.chemblid
        pubchem_id = bioactivity.assay.pubchem_id

        if pubchem:
            activity_name = bioactivity.activity_name
            standardized_value = bioactivity.value
            operator = u''
            standardized_units = u''
        else:
            activity_name = bioactivity.standard_name
            standardized_value = bioactivity.standardized_value
            operator = bioactivity.operator
            standardized_units = bioactivity.standardized_units

        obj = {
            'id': id,
            'compound': compound,
            'compoundid': compoundid,
            'target': target,
            'organism': organism,
            'activity_name': activity_name,
            'operator': operator,
            'standardized_value': standardized_value,
            'standardized_units': standardized_units,
            'chemblid': chemblid,
            'pubchem_id': pubchem_id,
        }
        data.append(obj)

    return {
        # json data
        'data_json': data,
        # 'table_link': data_csv_relpath,
        'length': length
    }
