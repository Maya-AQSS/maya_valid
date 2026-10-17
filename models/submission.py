# -*- coding: utf-8 -*-
from collections import Counter
from datetime import datetime, timezone
import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from odoo.addons.maya_moodle.models.moodlink import MoodleGatewayError
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


def _from_timestamp(ts):
  """ Timestamp de Moodle (UTC) a datetime naive en UTC, como los guarda Odoo """
  return datetime.fromtimestamp(ts, timezone.utc).replace(tzinfo = None) if ts else False


class Submission(models.Model):
  """
  Entrega de un alumno en una tarea de convalidaciones de Moodle.

  Es el inventario de lo que hay en Moodle: se sincroniza con la última entrega de cada
  alumno y marca como pendiente lo que es nuevo o ha cambiado desde la última vez. No
  descarga ni procesa nada.
  """

  _name = 'maya_valid.submission'
  _description = 'Entrega de convalidaciones en Moodle'
  _order = 'time_modified desc'
  _rec_name = 'moodle_user_info'

  task_id = fields.Many2one('maya_moodle.task_moodle', string = 'Tarea', required = True, ondelete = 'cascade', index = True)
  study_id = fields.Many2one('maya_core.study', string = 'Estudio')
  school_year_id = fields.Many2one('maya_core.school_year', string = 'Curso escolar')
  validation_type = fields.Integer(string = 'Tipo', help = 'Estudios (0) o competencias (1)')
  kind = fields.Selection([(REQUEST, 'Solicitud'), (CLAIM, 'Reclamación')], string = 'Entrega', required = True)

  moodle_submission_id = fields.Integer(string = 'Id entrega Moodle')
  moodle_user_id = fields.Integer(string = 'Id usuario Moodle', required = True)
  moodle_username = fields.Char(string = 'Usuario Moodle')
  moodle_firstname = fields.Char(string = 'Nombre (Moodle)')
  moodle_lastname = fields.Char(string = 'Apellidos (Moodle)')
  moodle_user_info = fields.Char(string = 'Alumno', compute = '_compute_moodle_user_info')

  student_id = fields.Many2one('maya_core.student', string = 'Estudiante', index = True,
    help = 'Vacío si el usuario de Moodle no se corresponde con ningún estudiante de Maya')

  # como en maya_valid.validation, el primer intento es el 1 (en Moodle es el 0)
  attempt_number = fields.Integer(string = 'Intento')
  moodle_status = fields.Char(string = 'Estado en Moodle')
  grading_status = fields.Char(string = 'Estado calificación')
  time_modified = fields.Datetime(string = 'Modificada en Moodle')
  files = fields.Json(string = 'Ficheros')
  file_count = fields.Integer(string = 'Nº ficheros')

  state = fields.Selection([
    ('pending', 'Pendiente'),
    ('processed', 'Procesada'),
    ('error', 'Error'),
  ], string = 'Estado', default = 'pending', required = True, index = True,
    help = 'Pendiente: nueva o modificada en Moodle desde la última vez que se procesó')
  last_sync = fields.Datetime(string = 'Última sincronización')

  _unique_task_user = models.Constraint('unique(task_id, moodle_user_id)',
    'Sólo puede haber una entrega por tarea y usuario de Moodle.')

  @api.depends('moodle_username', 'moodle_firstname', 'moodle_lastname')
  def _compute_moodle_user_info(self):
    for record in self:
      name = ', '.join(filter(None, [record.moodle_lastname, record.moodle_firstname])) or _('Sin datos')
      record.moodle_user_info = f'({record.moodle_username or record.moodle_user_id}) {name}'

  # ------------------------------------------------------------ sincronización

  @api.model
  def sync_from_moodle(self, validation_type, kind = REQUEST, study_abbr = None):
    """
    Sincroniza las entregas de las tareas de convalidaciones de Moodle.

    :param validation_type: STUDIES_VAL o COMPETENCY_VAL
    :param kind: REQUEST (solicitud) o CLAIM (reclamación)
    :param study_abbr: si se indica, solo las tareas de ese estudio (p. ej. 'DAW')
    :return: resumen por tarea y totales. Un fallo en una tarea no detiene las demás.
    """
    key = TASK_KEYS.get((validation_type, kind))
    if key is None:
      raise UserError(_('Tipo de convalidación o de entrega no válido.'))

    domain = [('key', '=', key)]
    if study_abbr:
      domain.append(('study_abbr', '=', study_abbr))
    tasks = self.env['maya_moodle.task_moodle'].search(domain)

    gateway = self.env['maya_moodle.moodlink']
    service_user = gateway.service_user()

    totals = Counter()
    summaries = []
    for task in tasks:
      summary = {'task_id': task.moodle_id, 'study': task.study_abbr}
      try:
        data = gateway.get_submissions(task.moodle_id, status = 'submitted', user = service_user)
      except MoodleGatewayError as e:
        _logger.warning('No se pudieron obtener las entregas de la tarea %s (%s): %s', task.moodle_id, task.study_abbr, e)
        summary['error'] = {'code': e.code, 'message': str(e.args[0]) if e.args else ''}
        totals['errors'] += 1
        summaries.append(summary)
        continue

      counts = self._sync_task(task, validation_type, kind, data.get('submissions') or [])
      summary.update(counts)
      totals.update(counts)
      summaries.append(summary)

    return {'tasks': summaries, 'totals': dict(totals)}

  def _sync_task(self, task, validation_type, kind, submissions):
    """ Crea o actualiza las entregas de una tarea. Devuelve los recuentos """
    study = self.env['maya_core.study'].search([('abbr', '=', task.study_abbr)], limit = 1)
    if not study:
      _logger.warning('La tarea %s tiene un estudio desconocido: %s', task.moodle_id, task.study_abbr)
    school_year = self.env['maya_core.school_year'].search([
      ('state', '=', '1'), ('company_id', '=', (study.company_id or self.env.company).id)], limit = 1)

    now = fields.Datetime.now()
    existing = {s.moodle_user_id: s for s in self.search([('task_id', '=', task.id)])}
    students = self._match_students([item['user'] for item in submissions])

    counts = Counter(received = len(submissions))
    to_create = []
    for item in submissions:
      user = item['user']
      files = item.get('files') or []
      vals = {
        'moodle_submission_id': item['id'],
        'moodle_username': user.get('username'),
        'moodle_firstname': user.get('firstname'),
        'moodle_lastname': user.get('lastname'),
        'attempt_number': item['attempt_number'] + 1,
        'moodle_status': item.get('status'),
        'grading_status': item.get('grading_status'),
        'time_modified': _from_timestamp(item.get('time_modified')),
        'files': files,
        'file_count': len(files),
        'last_sync': now,
      }
      student = students.get(user['id'])
      if not student:
        counts['unmatched'] += 1

      record = existing.get(user['id'])
      if not record:
        vals.update({
          'task_id': task.id,
          'study_id': study.id,
          'school_year_id': school_year.id,
          'validation_type': validation_type,
          'kind': kind,
          'moodle_user_id': user['id'],
          'student_id': student.id if student else False,
          'state': 'pending',
        })
        to_create.append(vals)
        counts['created'] += 1
        continue

      changed = record.attempt_number != vals['attempt_number'] or record.time_modified != vals['time_modified']
      if changed:
        vals['state'] = 'pending'
        counts['updated'] += 1
      else:
        counts['unchanged'] += 1
      if student and record.student_id != student:
        vals['student_id'] = student.id
      record.write(vals)

    if to_create:
      self.create(to_create)
    return counts

  def _match_students(self, users):
    """
    Relaciona usuarios de Moodle con estudiantes de Maya: primero por moodle_id y, si no,
    por NIA (el usuario de Moodle de los alumnos es su NIA). Al encontrarlo por NIA se
    guarda su moodle_id para la próxima vez.

    :return: {id usuario Moodle: maya_core.student}
    """
    Student = self.env['maya_core.student']
    moodle_ids = [str(u['id']) for u in users]
    usernames = [u['username'] for u in users if u.get('username')]
    found = Student.search(['|', ('moodle_id', 'in', moodle_ids), ('nia', 'in', usernames)])
    by_moodle_id = {s.moodle_id: s for s in found if s.moodle_id}
    by_nia = {s.nia: s for s in found}

    result = {}
    for u in users:
      student = by_moodle_id.get(str(u['id']))
      if not student and u.get('username') in by_nia:
        student = by_nia[u['username']]
        if not student.moodle_id:
          student.moodle_id = str(u['id'])
      if student:
        result[u['id']] = student
    return result
