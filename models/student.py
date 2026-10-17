# -*- coding: utf-8 -*-

from odoo import fields, models

class Student(models.Model):
  """
  Ejemplo de herencia de clase
  Herencia del modelo maya_core.student
  Lo que hace es modificar el modelo maya_core.student para incluir el campo maya_employee_id, que
  se añadirá a la tabla maya_core.student de la base de datos
  Ese campo es accesible por cualquier otro módulo
  """
  _inherit = 'maya_core.student'

  # un estudiante podría solicitar convalidaciones de dos ciclos diferentes 
  # (aunque a día de hoy no está permitido)
  validations_ids = fields.One2many('maya_valid.validation', 'student_id')