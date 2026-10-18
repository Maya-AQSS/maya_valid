# -*- coding: utf-8 -*-
import logging
import os

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from odoo.addons.maya_moodle.models.submission import SubmissionError
from ..support import submission_files
from .validation import STUDIES_VAL, COMPETENCY_VAL

_logger = logging.getLogger(__name__)

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
  zip_path = fields.Char(string = 'Fichero zip', readonly = True)
  folder_path = fields.Char(string = 'Carpeta descomprimida', readonly = True)

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
    result = self.sync_tasks(self.env['maya_moodle.task_moodle'].search(domain))

    # las entregas nuevas o cambiadas se procesan en segundo plano
    totals = result['totals']
    if totals.get('created') or totals.get('updated'):
      self.env.ref('maya_valid.cron_process_submissions').sudo()._trigger()
    return result

  @api.model
  def _prepare_task_vals(self, task):
    vals = super()._prepare_task_vals(task)
    if task.key in TASK_TYPES:
      vals['validation_type'], vals['kind'] = TASK_TYPES[task.key]
    return vals

  # ------------------------------------------------------------ procesamiento

  @api.model
  def _cron_process_validations(self):
    """ Cron: procesa las entregas pendientes de las tareas de convalidaciones """
    self._process_pending([('task_key', 'in', list(TASK_TYPES))])

  def _process(self):
    """
    Entrega de convalidaciones: descarga el zip en validations_path, lo descomprime y
    normaliza los nombres de los ficheros.

    <validations_path>/<curso>/<estudio>/[<id moodle>]_<APELLIDOS>,_<NOMBRE>/
        [<id moodle>][<intento>]_<APELLIDOS>,_<NOMBRE>.zip
        [<id moodle>][<intento>]_<APELLIDOS>,_<NOMBRE>/     <- descomprimido
    Los nombres llevan delante UC_ si es por competencias y REC_ si es una reclamación.
    """
    if self.task_key not in TASK_TYPES:
      return super()._process()

    files = self.files or []
    if len(files) != 1:
      raise SubmissionError('MFL', _('Sólo se admite la entrega de un único fichero (hay %d).') % len(files))
    file = files[0]
    if not file.get('filename', '').lower().endswith('.zip'):
      raise SubmissionError('NZP', _('El fichero entregado (%s) no es un zip.') % file.get('filename'))

    data = self.download_file(file)
    if not submission_files.is_zip(data):
      raise SubmissionError('NZP', _('El fichero entregado (%s) no es un zip válido.') % file.get('filename'))

    folder, name = self._storage_location()
    try:
      self.zip_path, self.folder_path = submission_files.save_and_extract(data, folder, name)
    except submission_files.BadSubmissionZip as e:
      raise SubmissionError('NZP', str(e))
    _logger.info('Entrega %s descargada en %s', self.id, self.folder_path)

  def _storage_location(self):
    """ Carpeta del alumno y nombre (sin extensión) de la entrega, como en el proceso antiguo """
    base = self.env['ir.config_parameter'].sudo().get_param('maya_valid.validations_path')
    if not base:
      raise UserError(_('No se ha configurado la carpeta de las convalidaciones (Ajustes > Convalidaciones).'))
    if not self.study_id:
      # es de la tarea, no de todas las entregas: no se para la cola
      raise SubmissionError('no_study', _('La tarea %s no tiene un estudio válido (%s).') % (self.task_id.moodle_id, self.task_id.study_abbr))

    # curso escolar: el de la entrega o, si no hay ninguno activo, el que corresponde a la fecha
    if self.school_year_id:
      year = self.school_year_id.date_init.year
    else:
      date = self.time_modified or fields.Datetime.now()
      year = date.year if date.month >= 9 else date.year - 1

    lastname = (self.moodle_lastname or 'SIN-APELLIDOS').upper()
    firstname = (self.moodle_firstname or 'SIN-NOMBRE').upper()
    prefix = ('UC ' if self.validation_type == COMPETENCY_VAL else '') + ('REC ' if self.kind == CLAIM else '')

    folder = os.path.join(base, '%s_%s' % (year, year + 1), self.study_id.abbr,
      submission_files.normalize_name('[%s] %s, %s' % (self.moodle_user_id, lastname, firstname)))
    name = submission_files.normalize_name('%s[%s][%s] %s, %s' % (
      prefix, self.moodle_user_id, self.attempt_number, lastname, firstname))
    return folder, name
