# -*- coding: utf-8 -*-

from odoo import api, models, fields
from datetime import date

import logging

_logger = logging.getLogger(__name__)

class AcademicRecord(models.Model):
  """
  Expedientes académicos que hay que generar de antiguos alumnos del Centro
  """

  _name = 'maya_valid.academic_record'
  _description = 'Expedientes académicos de antiguos alumnos del Centro'
  _order = 'write_date'

  validation_id = fields.Many2one('maya_valid.validation', string = 'Estudiante', required = True)
  state = fields.Selection([
      ('0', 'Pendiente'),
      ('1', 'No existe'),
      ('2', 'Finalizado')], string = 'Estado', required = True)
  
  info = fields.Text(string = 'Ciclo/curso', required = True)
  comments = fields.Text(string = 'Comentarios')

  generator_id = fields.Many2one('maya_core.employee', string = 'Generado por')
  generator_date_id = fields.Date(string = 'Fecha generación') 

  def write(self, vals):
    """
    Actualiza en la base de datos un registro
    """
   
    today = date.today()
    current_employee = self.env.user.maya_employee_id
  
    vals['generator_id'] = current_employee
    vals['generator_date_id'] = today

    return super(AcademicRecord, self).write(vals)
  
  @api.onchange('state')
  def _change_situation_validation(self):
    self.ensure_one()

    situation = '0'
    
    if self.state== '2':
      situation = '8'

    if self.state== '0':
      situation = '6'

    if self.state== '1':
      situation = '7'

    self.validation_id.sudo().write({
      'situation': situation
    })

    return