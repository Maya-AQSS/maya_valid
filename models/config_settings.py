# -*- coding: utf-8 -*-
from odoo import models, fields

class ResConfigSettings(models.TransientModel):
  _inherit = 'res.config.settings'

  validations_path = fields.Char(string = 'Carpeta de almacenamiento de las convalidaciones', config_parameter='maya_valid.validations_path')