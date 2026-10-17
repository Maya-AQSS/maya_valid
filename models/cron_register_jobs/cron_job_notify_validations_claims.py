# -*- coding: utf-8 -*-

from odoo import models, api
from datetime import date, timedelta, datetime
import logging


# Moodle
from ....maya_core.support.maya_moodleteacher.maya_moodle_connection import MayaMoodleConnection
from ....maya_core.support.maya_moodleteacher.maya_moodle_assigments import MayaMoodleAssignments
from ....maya_core.support.maya_moodleteacher.maya_moodle_user import MayaMoodleUser
from ....maya_core.support.maya_moodleteacher.maya_moodle_user import MayaMoodleUsers

from ....maya_core.models.cron_register_jobs.cron_job_enrol_users import CronJobEnrolUsers

from ....maya_core.support.maya_logger.exceptions import MayaException

from ..validation import STUDIES_VAL, COMPETENCY_VAL

_logger = logging.getLogger(__name__)

class CronJobNotifyValidationsClaims(models.TransientModel):
  _name = 'maya_valid.cron_job_notify_validations_claims'

  @api.model
  def cron_notify_validations_claims(self, validation_classroom_id, course_id, validation_claim_task_id, type = STUDIES_VAL):
    """
    Publica notificaciones sobre las reclamaciones de convalidaciones 
    correction notification indica si es una notificación para realizar una corrección sobre una notificación anterior
    """
    # comprobaciones iniciales
    if validation_classroom_id == None:
      _logger.error("CRON: validation_classroom_id no definido")
      return
    
    if validation_claim_task_id == None:
      _logger.error("CRON: validation_task_id no definido")
      return
    
    if course_id == None:
      _logger.error("CRON: course no definido")
      return
    
    validations = self.env['maya_valid.validation'].search([('course_id', '=', course_id), ('validation_type','=', type)])

    if len(validations) == 0:
      return
    
    try:
      conn = MayaMoodleConnection( 
        user = self.env['ir.config_parameter'].get_param('maya_core.moodle_user'), 
        moodle_host = self.env['ir.config_parameter'].get_param('maya_core.moodle_url')) 
    except Exception:
      raise Exception('No es posible realizar la conexión con Moodle')
    
    current_sy = (self.env['maya_core.school_year'].search([('state', '=', 1)])) # curso escolar actual  

    if len(current_sy) == 0:
      raise MayaException(
          _logger, 
          'No se ha definido un curso actual',
          50, # critical
          comments = '''Es posible que no se haya marcado como actual ningún curso escolar''')
    else:
      current_school_year = current_sy[0]
        
    # obtención de las tareas entregadas
    assignments = MayaMoodleAssignments(conn, 
      course_filter=[validation_classroom_id], 
      assignment_filter=[validation_claim_task_id])
    
    if len(assignments) == 0:
      raise MayaException(
          _logger, 
          'No se ha encontrado la tarea para la reclamación de convalidaciones (moodle_id: {})'.format(validation_claim_task_id),
          50, # critical
          comments = '''Es posible que la tarea con moodle_id:{} no exista en moodle o no
                      exista dentro del curso con moodle_id: {}. 
                      Es posible que se haya creado un nuevo curso escolar y no se haya
                      actualizado los moodle_id dentro de Maya'''.
                      format(validation_claim_task_id, validation_classroom_id))
    
    submissions = assignments[0].submissions()
    
    for validation in validations:

      # si no ha sido reclamada se notifica por otro cronjob
      if not validation.claimed:
        continue

      # obtengo la primera entrega que tenga como estudiante al que se indica en la convalidación
      submission = next((sub for sub in submissions if sub.userid == int(validation.student_id.moodle_id)), None)
      if submission == None:
        _logger.error(f'No es posible encontrar en la tarea de Moodle {validation_claim_task_id} la entrega del usuario id Aules@{validation.student_id.moodle_id}:Maya@{validation.student_id}')
        continue
      
      # está finalizada
      if validation.state == '13':
        submission.unlock()
        submission.save_grade(4, new_attempt = False, feedback = validation.create_finished_notification_claim_message())
        validation.write({
          'state': '15'  
        })
        submission.lock()