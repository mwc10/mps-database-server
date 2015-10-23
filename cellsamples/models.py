# coding=utf-8

"""

CellSamples Models

"""

from django.db import models

# Use our own model base classes instead of models.Model
from mps.base.models import LockableModel, RestrictedModel, FlaggableModel


class Organ(LockableModel):
    organ_name = models.CharField(max_length=255, unique=True)

    class Meta(object):
        ordering = ('organ_name', )

    def __unicode__(self):
        return u'{}'.format(self.organ_name)


class CellType(LockableModel):

    # TODO refactor to be a FK instead, should not be using a charfield here
    SPECIESTYPE = (
        ('Human', 'Human'),
        ('Rat', 'Rat'),
        ('Mouse', 'Mouse'),
    )
    cell_type = models.CharField(max_length=255,
                                 help_text='Example: hepatocyte, muscle, kidney, etc')
    species = models.CharField(max_length=10,
                               choices=SPECIESTYPE, default='Human', null=True,
                               blank=True)

    # TODO TO BE REMOVED
    cell_subtype = models.ForeignKey('CellSubtype')
    organ = models.ForeignKey('Organ')

    class Meta(object):
        verbose_name = 'Cell Type'
        ordering = ('species', 'cell_type', 'cell_subtype',)
        unique_together = [('cell_type', 'species', 'cell_subtype')]

    def __unicode__(self):
        return u'{} ({} {})'.format(
            self.cell_type,
            self.species,
            self.organ
        )

    # Will this be useful?
    def get_absolute_url(self):
        return "/cellsamples/celltype/{}".format(self.id)


class CellSubtype(LockableModel):
    class Meta(object):
        ordering = ('cell_subtype', )

    cell_subtype = models.CharField(max_length=255, unique=True,
                                    help_text="Example: motor (type of neuron), "
                                              "skeletal (type of muscle), etc.")

    cell_type = models.ForeignKey(CellType, null=True, blank=True)

    def __unicode__(self):
        return u'{}'.format(self.cell_subtype)


class Supplier(LockableModel):
    class Meta(object):
        ordering = ('name', )
    name = models.CharField(max_length=255, unique=True)
    phone = models.CharField(max_length=255, blank=True)
    address = models.CharField(max_length=255, blank=True)

    def __unicode__(self):
        return u'{}'.format(self.name)


class Biosensor(LockableModel):
    class Meta(object):
        ordering = ('name', )
    name = models.CharField(max_length=255, unique=True)
    supplier = models.ForeignKey('Supplier')
    product_id = models.CharField(max_length=255, blank=True)
    lot_number = models.CharField(max_length=255, blank=True,
                                  verbose_name='Lot#')
    description = models.CharField(max_length=512, blank=True)

    def __unicode__(self):
        return u'{}'.format(self.name)


class CellSample(FlaggableModel):

    cell_type = models.ForeignKey('CellType')
    cell_subtype = models.ForeignKey('CellSubtype')

    # TODO TO BE REMOVED
    # cell_source CONSIDERED UNINTUITIVE
    CELLSOURCETYPE = (
        ('Freshly isolated', 'Freshly isolated'),
        ('Cryopreserved', 'Cryopreserved'),
        ('Cultured', 'Cultured'),
        ('Other', 'Other'),
    )

    cell_source = models.CharField(max_length=20,
                                   choices=CELLSOURCETYPE, default='Primary',
                                   null=True, blank=True)

    notes = models.TextField(blank=True)
    receipt_date = models.DateField()

    # SAMPLE

    supplier = models.ForeignKey('Supplier')
    barcode = models.CharField(max_length=255, blank=True, verbose_name='Barcode/Lot#')
    product_id = models.CharField(max_length=255, blank=True)

    # PATIENT

    GENDER_CHOICES = (
        ('N', 'Not-specified'),
        ('F', 'Female'),
        ('M', 'Male'),
    )
    patient_age = models.IntegerField(null=True, blank=True)
    patient_gender = models.CharField(max_length=1, choices=GENDER_CHOICES,
                                      default=GENDER_CHOICES[0][0],
                                      blank=True)
    patient_condition = models.CharField(max_length=255,
                                         blank=True)

    # ISOLATION

    isolation_datetime = models.DateField("Isolation",blank=True,
                                          null=True)
    isolation_method = models.CharField("Method", max_length=255,
                                        blank=True)
    isolation_notes = models.CharField("Notes", max_length=255,
                                       blank=True)

    # VIABILITY

    viable_count = models.FloatField(null=True, blank=True)

    # Removed: Deemed confusing/not useful
    # VIABLE_COUNT_UNIT_CHOICES = (
    #     ('N', 'Not-specified'),
    #     ('A', 'per area'),
    #     ('V', 'per volume'),
    # )
    # viable_count_unit = models.CharField(max_length=1,
    #                                      choices=VIABLE_COUNT_UNIT_CHOICES,
    #                                      default=VIABLE_COUNT_UNIT_CHOICES[0][
    #                                          0], blank=True)

    percent_viability = models.FloatField(null=True, blank=True)
    cell_image = models.ImageField(upload_to='cellsamples',
                                   null=True, blank=True)
    class Meta(object):
        verbose_name = 'Cell Sample'
        ordering = ('-receipt_date', )

    def __unicode__(self):
        if self.barcode:
            return u'{} {} ({}-{})'.format(
                self.cell_subtype,
                self.cell_type,
                self.supplier,
                self.barcode
            )
        else:
            return u'{} {} ({})'.format(
                self.cell_subtype,
                self.cell_type,
                self.supplier
            )

    # Will this be useful?
    def get_absolute_url(self):
        return "/cellsamples/cellsample/{}".format(self.id)
