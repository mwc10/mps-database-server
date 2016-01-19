import sys, os
sys.path.append('/home/mps/mps-database-server')
os.environ['DJANGO_SETTINGS_MODULE'] = 'mps.settings'
from django.conf import settings
import datetime

from compounds.models import Compound, chembl_compound
from bioactivities.models import Assay, Target, Bioactivity
from bioactivities.models import chembl_target, chembl_assay

from bioservices import ChEMBL as ChEMBLdb
from bioservices.services import BioServicesError

from django.db import connection

FIELDS = {
    'reference': 'reference',
    'target_chemblid': 'target',
    'bioactivity_type': 'bioactivity_type',
    'ingredient_cmpd_chemblid': 'compound',
    'value': 'value',
    'units': 'units',
    'assay_chemblid': 'assay',
    'parent_cmpd_chemblid': 'parent_compound',
    'operator': 'operator',
    'activity_comment': 'activity_comment',
    'name_in_reference': 'name_in_reference',
    'target_confidence': 'target_confidence'
}



def run(days=180):
    """Run as::

      $ python manage.py runscript update_activities

    By default, updates bioactivities of compounds that were never updated
    or updates 180 days ago.

    To force updating bioactivities for all compounds, give 0 days argument
    as follows::

        $ python manage.py runscript update_activities --script-args=0

    """

    try:
        days = int(days)
    except ValueError:
        days = 180

    chembl = ChEMBLdb()

    #for table, func in [
    #    (Compound, chembl.get_compounds_activities),
    #    (Target, chembl.get_target_bioactivities),
    #    (Assay, chembl.get_assay_bioactivities), ]:
    count = skip = error = ncomp = 0
    # will iterate over all compounds one-by-one
    for compound in Compound.objects.all():

        # if no updates were made, last_update is None
        if (compound.last_update is None or
            (datetime.date.today() - compound.last_update) >=
             datetime.timedelta(days)):
            ncomp += 1

            try:
                acts = chembl.get_compounds_activities(str(compound.chemblid))
            except BioServicesError:
                continue

            try:
                for act in acts['bioactivities']:
                    act = {FIELDS[key]: value for key, value in act.items()
                            if key in FIELDS}

                    tid, aid, cid, pid = (act['target'], act['assay'],
                        act['compound'], act['parent_compound'])
                    try:
                        parent = Compound.objects.get(chemblid=pid)
                    except Compound.DoesNotExist:
                        try:
                            parent = Compound.objects.create(locked=True, **chembl_compound(pid))
                            print "Added Compound:", parent.name
                        except ValueError:
                            error += 1
                            continue

                    try:
                        target = Target.objects.get(chemblid=tid)
                    except Target.DoesNotExist:
                        try:
                            target = Target.objects.create(locked=True, **chembl_target(tid))
                        except ValueError:
                            error += 1
                            continue

                    try:
                        assay = Assay.objects.get(chemblid=aid)
                    except Assay.DoesNotExist:
                        try:
                            assay = Assay.objects.create(locked=True, **chembl_assay(aid))
                        except ValueError:
                            error += 1
                            continue

                    try:
                        activity = Bioactivity.objects.get(
                            target=target, assay=assay, compound=compound)
                    except Bioactivity.DoesNotExist:

                        (act['target'], act['assay'], act['compound'],
                            act['parent_compound']) = (
                            target, assay, compound, parent)

                        try:
                            ba = Bioactivity.objects.create(locked=True, **act)
                        except ValueError:
                            error += 1
                        except Exception as err:
                            for key, val in act.items():
                                if isinstance(val, str):
                                    print('{}: ({}) {}'.format(key, len(val), val))
                            raise err
                        else:
                            count += 1
                    else:
                        skip += 1
            except:
                print "An error occured:", compound.name, acts

            compound.last_update = datetime.date.today()
            compound.save()

    print('{} bioactivities were added, {} were found in the database, and '
          '{} failed due to value errors.'.format(count, skip, error))

    print 'Updating bioactivity units...'
    cursor = connection.cursor()

    cursor.execute(
        '''
        UPDATE bioactivities_bioactivity
        SET standardized_units = NULL,
            standard_name = NULL,
            standardized_value = NULL;

        --no mass is needed in data conversion
        UPDATE public.bioactivities_bioactivity as v
        SET standard_name = s.standard_name,
        standardized_units=s.standard_unit,
            standardized_value=value*scale_factor
        FROM public.bioactivities_bioactivitytype as s
        WHERE v.bioactivity_type = s.chembl_bioactivity and
        v.units=s.chembl_unit and s.mass_flag='N';

        --mass is needed in data conversion
        UPDATE public.bioactivities_bioactivity as v
        SET standard_name = s.standard_name,
        standardized_units=s.standard_unit,
            standardized_value=value*scale_factor/c.molecular_weight
        FROM public.bioactivities_bioactivitytype as s,
        public.compounds_compound as c
        WHERE v.bioactivity_type = s.chembl_bioactivity and
        v.units=s.chembl_unit and v.compound_id =c.id and s.mass_flag='Y';
        '''
    )

    print 'Units updated'

# A second run is useful to catch newly added compounds,
# but just calling run is somewhat inefficient (it would run through every compound again)
#run(0)
