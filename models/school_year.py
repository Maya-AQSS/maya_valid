# -*- coding: utf-8 -*-

import datetime
from odoo import api, models, fields, _

import logging

_logger = logging.getLogger(__name__)

class SchoolYear(models.Model):
  """
  Herencia de clase
  Herencia del modelo maya_core.school_year
  Lo que hace es modificar el modelo maya_core.school_year para incluir 
  la fecha de incio de las convalidaciones
  """
  _inherit = 'maya_core.school_year'

  # inicio real de las convalidaciones
  date_init_valid = fields.Date(string = 'Inicio periodo convalidaciones', compute = '_compute_date_init_valid', readonly = False, store = True)
  # Fecha final de las convalidaciones
  date_end_valid = fields.Date(string = 'Fin periodo convalidaciones', compute = '_compute_date_end_valid', readonly = True)
  # inicio periodo convalidaciones por acreditación de competencias
  date_init_valid_competency = fields.Date(string = 'Inicio periodo conv. competencias', compute = '_compute_date_init_valid_competency', readonly = False, store = True) 
  # Fecha final periodo convalidaciones por acreditación de competencias
  date_end_valid_competency = fields.Date(string = 'Fin periodo conv. competencias', compute = '_compute_date_end_valid_competency', readonly = False, store = True)

  @api.depends('date_init_lective')
  def _compute_date_init_valid(self):
    for record in self:
      if record.date_init_lective == False:
        record.date_init_valid = ''
      else:
        record.date_init_valid = record.date_init_lective

  @api.depends('date_init_valid')
  def _compute_date_end_valid(self):
    for record in self:
      if record.date_init_valid == False:
        record.date_end_valid = ''
      else:
        record.date_end_valid =  record.date_init_valid + datetime.timedelta(days = 30)

  @api.depends('date_end_valid')
  def _compute_date_init_valid_competency(self):
    for record in self:
      if record.date_end_valid == False:
        record.date_init_valid_competency = ''
      else:
        record.date_init_valid_competency =  record.date_end_valid - datetime.timedelta(days = 7)

  @api.depends('date_extraord1_exam_end')
  def _compute_date_end_valid_competency(self):
    for record in self:
      if record.date_extraord1_exam_end == False:
        record.date_end_valid_competency = ''
      else:
        record.date_end_valid_competency =  record.date_extraord1_exam_end

  def update_dates(self):
    self.dates['init_valid'] = { 
      'date': self.date_init_valid,
      'desc': 'Inicio periodo de convalidaciones', 
      'type': 'G'
    }

    self.dates['end_valid'] = { 
      'date': self.date_end_valid,
      'desc': 'Fin periodo de convalidaciones', 
      'type': 'G'
    }

    self.dates['init_valid_competency'] = { 
      'date': self.date_init_valid_competency ,
      'desc': 'Inicio periodo de conv. por acreditación de competencias', 
      'type': 'G'
    }

    self.dates['end_valid_competency'] = { 
      'date': self.date_end_valid_competency ,
      'desc': 'Fin periodo de conv. por acreditación de competencias', 
      'type': 'G'
    }

    return super(SchoolYear, self).update_dates()