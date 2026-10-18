# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError

from .validation import STUDIES_VAL, COMPETENCY_VAL

REQUEST = 'request'
CLAIM = 'claim'

# clave de la tarea de Moodle (maya_moodle.task_moodle.key) según tipo de convalidación y entrega
TASK_KEYS = {
  (STUDIES_VAL, REQUEST): 'validation',
  (STUDIES_VAL, CLAIM): 'validation_claim',
  (COMPETENCY_VAL, REQUEST): 'competence',
  (COMPETENCY_VAL, CLAIM): 'competence_claim',
}
TASK_TYPES = {key: val_kind for val_kind, key in TASK_KEYS.items()}


class Submission(models.Model):
  """
  Amplía las entregas de Moodle (maya_moodle.submission) con los datos de las
  tareas de convalidaciones: tipo de convalidación y si es solicitud o reclamación.
  """

  _inherit = 'maya_moodle.submission'

  # sólo tienen valor en las entregas de tareas de convalidaciones
  validation_type = fields.Integer(string = 'Tipo', help = 'Estudios (0) o competencias (1)')
  kind = fields.Selection([(REQUEST, 'Solicitud'), (CLAIM, 'Reclamación')], string = 'Entrega')

  @api.model
  def sync_validations(self, validation_type, kind = REQUEST, study_abbr = None):
    """
    Sincroniza las entregas de las tareas de convalidaciones de Moodle.

    :param validation_type: STUDIES_VAL o COMPETENCY_VAL
    :param kind: REQUEST (solicitud) o CLAIM (reclamación)
    :param study_abbr: si se indica, solo las tareas de ese estudio (p. ej. 'DAW')
    :return: resumen por tarea y totales (ver maya_moodle.submission.sync_tasks)
    """
    key = TASK_KEYS.get((validation_type, kind))
    if key is None:
      raise UserError(_('Tipo de convalidación o de entrega no válido.'))

    domain = [('key', '=', key)]
    if study_abbr:
      domain.append(('study_abbr', '=', study_abbr))
    return self.sync_tasks(self.env['maya_moodle.task_moodle'].search(domain))

  @api.model
  def _prepare_task_vals(self, task):
    vals = super()._prepare_task_vals(task)
    if task.key in TASK_TYPES:
      vals['validation_type'], vals['kind'] = TASK_TYPES[task.key]
    return vals
