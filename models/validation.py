# -*- coding: utf-8 -*-

from odoo import api, models, fields
from odoo.exceptions import ValidationError

from odoo.exceptions import AccessDenied 

import datetime
import logging
import base64
import os, json

from unicodedata import normalize

from ..support.helper import create_HTML_list_from_list
from ...maya_core.support.maya_logger.exceptions import MayaException

_logger = logging.getLogger(__name__)

STUDIES_VAL = 0
COMPETENCY_VAL = 1

class Validation(models.Model):
  """
  Define la entrega de convalidaciones por parte del alumnado
  """
  _name = 'maya_valid.validation'
  _description = 'Solicitud convalidación'
  _rec_name = 'student_info' 
  _order = 'student_surname'

  # tipo de convalidacion, por estudios o por experiencia
  validation_type = fields.Integer(string = 'Tipo',  help = 'Estudios o experiencia laboral')

  company_id = fields.Many2one(
      'res.company', 
      string='Tipo de enseñanza',
      required=True, 
      default=lambda self: self.env.company,
      index=True
  )

  school_year_id = fields.Many2one('maya_core.school_year', string = 'Curso escolar')
  
  student_id = fields.Many2one('maya_core.student', string = 'Estudiante', required = True)
  student_name = fields.Char(related = 'student_id.name') 
  student_surname = fields.Char(related = 'student_id.surname', store = True) 
  student_nia = fields.Char(related = 'student_id.nia') 
  student_info = fields.Char(string = 'Estudiante', compute = '_compute_full_student_info')

  study_id = fields.Many2one('maya_core.study', string = 'Estudio', required = True)
  study_abbr = fields.Char(string = 'Estudio', related = 'study_id.abbr')

  validation_subjects_ids = fields.One2many('maya_valid.validation_subject', 'validation_id', 
     string = 'Módulos que se solicita convalidar')

  validation_subjects_not_for_correction_ids = fields.One2many('maya_valid.validation_subject', 
  'validation_id', 
    string = 'Módulos que se solicita convalidar', 
    domain = [('state', '!=', '1')],
    compute = '_compute_validation_subjects_not', readonly = False)

  validation_subjects_for_correction_ids = fields.One2many('maya_valid.validation_subject', 'validation_id', 
    string = 'Módulos pendientes de subsanación',
    domain = [('state', '=', '1')],
    compute = '_compute_validation_subjects', readonly = False)
     
  validation_subjects_info = fields.Char(string = 'Res. / Rev. / Fin. / Sol.', compute = '_compute_validation_subjects_info')

  # aporta información extra sobre el estado de la convalidación  
  situation = fields.Selection([
      ('0', ' '),
      ('1', 'Pendiente de notificación al alumno'),
      ('2', 'Notificación enviada'),
      ('3', 'Nuevo envio de documentación'),
      ('4', 'Subsanación fuera de plazo'),
      ('5', 'Notificación rectificada (pendiente envio)'),
      ('6', 'Pendiente expediente CEED'),
      ('7', 'Expediente no localizado'),
      ('8', 'Expediente CEED generado'),
      ], string = 'Situación', default = '0',
      readonly = True)

  # TODO que hacer con instancia superior si tardan en responder??
  # una opción es pasado un tiempo enviar el mail de confirmación al alumno
  # y finalizarla parcialmente
  state = fields.Selection([
      ('0', 'Sin procesar'),
      ('1', 'En proceso'),
      ('2', 'Subsanación'),
      ('3', 'Instancia superior'),
      ('4', 'Subsan. / Inst. superior'),
      ('5', 'Resuelta'),
      ('6', 'En proceso de revisión'),
      ('7', 'En proceso de revisión (parcial)'), # algunas revisadas, otras aun resueltas y algunas elevadas a una instancia superior
      ('8', 'Revisada'),
      ('9', 'Revisada parcialmente'),
      ('10', 'En proceso de finalización (parcial)'),
      ('11', 'Finalizada parcialmente'),
      ('12', 'En proceso de finalización'),
      ('13', 'Finalizada'), # todas las convalidaciones finalizadas pero sin notificación al alumno
      ('14', 'Cerrada parcialmente'), # solo se indica el estado, no se hace nada con él
      ('15', 'Cerrada'),
      ('16', 'Reclamación'),
      ('17', 'Revisada tras reclamación'),
      ], string ='Estado', help = 'Estado de la convalidación', 
      default = '0', compute = '_compute_state', store = True)
  
  # fecha de solicitud de la subsanación
  correction_date = fields.Date(string = 'Fecha subsanación', 
                                help = 'Fecha de publicación de la subsanación')
  
  correction_date_end = fields.Date(string = 'Fecha fin subsanación', 
                                    help = 'Fin de plazo de la subsanación',
                                    compute = '_compute_correction_date_end')

  # subsanación por razones de forma. Hace referencia a la entrega en si, no a 
  # cada uno de los módulos
  correction_reason = fields.Selection([
    ('MFL', 'Sólo se admite la entrega de un único fichero.'),
    ('NZP', 'La documentación aportada no se encuentra en un único fichero zip comprimido.'),
    ('NNX', 'No se encuentra un fichero llamado anexo o hay más de uno.'),
    ('ANC', 'Anexo no cumplimentado correctamente. Campos obligatorios no rellenados.'),
    ('ANP', 'Anexo no cumplimentado correctamente. Tipo (convalidación/aprobado con anterioridad) no indicado.'),
    ('ANE', 'Anexo no cumplimentado correctamente. No se ha indicado qué estudios reglados y/u otra documentación y/o ciclos formativos se estudiaron en el Centro.'),
    ('SNF', 'Documento no firmado electrónicamente'),
    ('VIN', 'El trámite solicitado se gestiona a través de otra vía.'),
    ('INT', 'Ver convalidaciones módulos'), # subsanaciones específicas de módulos
    ('ERR1', 'Error al notificar una subsanación que no era'), 
    ('ERR2', 'Error al notificar los detalles de una subsanación'), 
    ('ANL', 'No es posible abrir el anexo.'),
    ('MNE', 'Se han indicado módulos que no existen.'),
    ('ANU', 'Anexo no cumplimentado correctamente. En uno o más módulos no se han indicado las unidades de competencia presentadas para la convalidación.'),
    ], string ='Razón de la subsanación', 
    help = 'Permite indicar el motivo por el que se solicita la subsanación')
  
  # numeración basada en 1: 1,2,3,4...
  attempt_number = fields.Integer(string = 'Número de entregas realizadas', default = 1,
                                  readonly = True, 
                                  help = 'Indica el número actual de veces que ha realizado la subida de la documentación debido a subsanaciones')

  documentation = fields.Binary(string = "Documentación")
  documentation_filename = fields.Char(
        string='Nombre del fichero',
        compute='_compute_documentation_filename'
    )
  
  info = fields.Text(string = "Información", compute = '_compute_info')

  sign_data = fields.Text(string = "Firma electrónica datos")
  sign_info = fields.Text(string = "Firma electrónica", compute = '_compute_sign_info')
  sign_state = fields.Boolean(compute = '_compute_sign_info')

  remarks = fields.Text(string = 'Observaciones subsanación', default = '', help = 'Observaciones que se muestran en el mensaje de subsanación. Sólo admite un párrafo') # observaciones subsanación

  # indica si la convalidación ha sido reclamada
  claimed = fields.Boolean(default = False)
  remarks_claim = fields.Text(string = 'Observaciones reclamación', default = '', help = 'Observaciones que se muestran en el mensaje de resolución de la reclamación. Sólo admite un párrafo') # observaciones subsanación

  def _default_locked(self):
    if (self.state == '2' and self.situation == '2') or self.situation == '5' or self.situation == '6': 
      return True
    else:
      return False
    
  locked = fields.Boolean(default = _default_locked, store = False, readonly = True)

  is_state_read_only = fields.Boolean(compute = '_compute_is_state_read_only')
  
  _unique_validation = models.Constraint('unique(school_year_id, student_id, study_id, validation_type)', 'Sólo puede haber una convalidación de un tipo por estudiante, estudio y curso escolar.')  
   
  def write(self, vals):
    """
    Actualiza en la base de datos un registro
    """
    # impide que se realice más de una subsanación (INT)
    if self.situation == '3':
      if 'validation_subjects_ids' in vals and \
         'validation_subjects_for_correction_ids' in vals:
        
        # comprobación de que no haya ningún estado nuevo diferente de resulto o instancia superior
        for val in vals['validation_subjects_ids']:
          if val[2] != False and 'state' in val[2] and (val[2]['state'] =='0' or val[2]['state'] =='1'):
            raise ValidationError('Sólo se permite una subsanación. Todas las convalidaciones tienen, por tanto, que estar resueltas o enviadas a una instancia superior')
        
        # comprobación de que no quede ninguna en estado de subsanación. Si quedase al menos 1 
        # implicaria volver a realizar el proceso de subsanación y sólo se permite una vez
        for vfc in vals['validation_subjects_for_correction_ids']:
          val = next((vl for vl in vals['validation_subjects_ids'] if vl[1] == vfc[1]), None)
          if val[2] == False:
            raise ValidationError('Sólo se permite una subsanación. Todas las convalidaciones tienen, por tanto, que estar resueltas o enviadas a una instancia superior')

        
        vals['situation'] = '0'

    return super(Validation, self).write(vals)

  def create_correction(self, reason, comment = '') -> str:
    """
    Modifica la convalidación asignando los parámetros de subsanación
    Devuelve la notificación en formato HTML
    """
    if reason == None:
      raise Exception('Es necesario definir una razón para la subsanación')
    
    self.correction_date = datetime.datetime.today()
    
    footer = """
      <br>\
      <p><strong>Se recomienda la visualización del <a href="https://gvaedu.sharepoint.com/:v:/s/Documentar-46025799-CENTREPBLICDEDUCACIADISTNCIACEED-Departament-InformticaiComunicacions/Eek43EDYl_dCug3-d7iuO6IBPKmtC6Kx17JashINScIsiA?e=fOINLH">vídeo sobre convalidaciones</a> para poder realizar el proceso de forma correcta.</strong></p>
      <br>\
      <p>Se abre un periodo de subsanación de 15 días naturales a contar desde el día de publicación de este mensaje para reenviar \
        a través de esta misma tarea la documentación necesaria para corregir los errores. \
          Si pasado este periodo no se subsana el error, la(s) convalidación(es) afectadas se considerarán rechazadas.</p>
      <p>Recuerde enviar de nuevo TODA la documentación, incluso la ya entregada en envios previos</p>   
      <p><strong>Fin de período de subsanación</strong>: {0}</p>
      """.format(self.correction_date_end)

    # si la notificación previa es erronea
    prebody = ''
    if reason[:3] == 'ERR':
      prebody = """
          <p><strong>ATENCIÓN:</strong> La notificación previa fue enviada de manera errónea debido a un error administrativo. Esta notificación sustituye a la anterior. Disculpe las molestias</p>"""

    if reason == 'ERR1':
      body = prebody + '<p>Su convalidación se encuentra en estado: <strong>EN TRÁMITE</strong></p>.'

      self.write({ 
        'correction_reason': False,
        'state': '1', # Es posible que no sea necesario poner el estado. La propia convalidación lo calculará
        'correction_date': False
      })

      return body
    
    self.write({ 
      'correction_reason': reason,
      'state': '2',
      'correction_date': self.correction_date
    })
    
    # las causas viene definidas en cada uno de los módulos
    if reason in ('INT', 'ERR2'): 
      val_for_correction = [ '(' + val.subject_id.code + '/' + val.subject_id.abbr + ') ' 
                            + (dict(val._fields['correction_reason'].selection).get(val.correction_reason)) 
                            for val in self.validation_subjects_ids if val.state == '1']
      
      body = prebody + create_HTML_list_from_list(val_for_correction, 
                                                  'No es posible realizar la convalidación solicitada por los siguientes motivos:', 
                                                  ident = False)
    else:
      body = """
          <p>No es posible realizar la convalidación solicitada por los siguientes motivos:</p>
          <p style="padding-left: 1rem">(01) {0}</p>
          """.format(dict(self._fields['correction_reason'].selection).get(reason))
      
    remarks = ''
    if self.remarks and len(self.remarks) > 0:
        remarks = """
           <p><strong>Observaciones del convalidador</strong><p>
           <p>{0}</p>""".format(self.remarks)

    feedback = body + comment + remarks + footer

    return feedback

  def create_table_notification(self) -> str:
    """
    Crea las tablas de la resolución, tanto las negativas como las positivas
    Es válida para resolucion inicial com para reclamaciones
    """
    need_table_denied = False

    table = '<br><table class="table table-striped table-sm"><thead><tr><th>Código</th><th>Módulo</th><th>Tipo</th><th>Aceptada</th><th>Calificación</th></tr></thead><tbody>'
    
    for val in self.validation_subjects_ids:
      row = '<tr>'
      row += f'<td>{val.subject_id.code}</td>'
      row += f'<td style="padding-left:1rem">{val.subject_id.name}</td>'
      row += f'<td style="padding-left:1rem">{dict(val._fields["validation_type"].selection).get(val.validation_type)}</td>'

      if val.validation_type == 'ca':
        row += f'<td>--</td>'
      else:
        row += f'<td style="text-align: center">{dict(val._fields["accepted"].selection).get(val.accepted)}</td>'

      if val.accepted == '1':
        row += f'<td style="text-align: center">{dict(val._fields["mark"].selection).get(val.mark)}</td>'
      else:
        row += '<td>--</td>'
        
      if val.accepted == '2':
        need_table_denied = True

      row += '</tr>'

      table += row

      val.state = '7'

    table += '</tbody></table>'

    table_denied = ''
    if need_table_denied:

      table_denied = '<h6>Las causas de los rechazos son:</h6> \
        <br><table class="table table-striped table-sm"><thead><tr><th>Código</th><th>Módulo</th><th>Razón rechazo</th></tr></thead><tbody>'

      for val in self.validation_subjects_ids:
        if val.accepted == '1':
          continue
        
        row = '<tr>'
        row += f'<td>{val.subject_id.code}</td>'
        row += f'<td style="padding-left:1rem">{val.subject_id.name}</td>'
        row += f'<td style="padding-left:1rem">{val.comments}</td>'
        row += '</tr>'

        table_denied += row

      table_denied += '</tbody></table>'

    return table + table_denied
   
  def create_finished_notification_message(self) -> str:
    """
    Crea el mensaje de notificación de resolución de la convalidación
    Devuelve la notificación en formato HTML
    """
    body = '<h6>El proceso de convalidación solicitado ya ha sido finalizado con la siguiente resolución:</h6>'
    
    if self.situation == '4' and not len(self.validation_subjects_ids):  # fuera de plazo
      body_cont = '<p>La convalidación no ha sido admitida a trámite por finalización del plazo de subsanación.</p>'
      return body + body_cont

    tables = self.create_table_notification()

    feedback = body + tables

    return feedback

  
  def create_finished_notification_claim_message(self) -> str:
    """
    Crea el mensaje de notificación de resolución de la reclamación de la convalidación
    Devuelve la notificación en formato HTML
    """
    body = '<h6>El proceso de reclamación de la convalidación solicitado ya ha sido finalizado con la siguiente resolución:</h6>'

    tables = self.create_table_notification()

    remarks = '''
           <p><strong>Comentarios:</strong><p>
           <p>{0}</p>'''.format(self.remarks_claim)
  
    feedback = body + tables + remarks

    return feedback
  
  @api.depends('correction_date')
  def _compute_correction_date_end(self):
    for record in self:
      if record.correction_date == False:
        record.correction_date_end = False
      else:
        record.correction_date_end = record.correction_date + datetime.timedelta(days = 15)

  def _compute_full_student_info(self):
    for record in self:
      if record.student_nia == False:
        record.student_info = record.student_surname + ', ' + record.student_name
      else: 
        record.student_info = '(' + record.student_nia + ') ' + record.student_surname + ', ' + record.student_name

  def _compute_validation_subjects_info(self):
    for record in self:
        num_resolved = len([val for val in record.validation_subjects_ids if int(val.state) >= 3])
        num_reviewed = len([val for val in record.validation_subjects_ids if int(val.state) == 4 or int(val.state) >= 6])
        num_finished = len([val for val in record.validation_subjects_ids if int(val.state) >= 6])
        record.validation_subjects_info = f'{num_resolved} / {num_reviewed} / {num_finished} / {len(record.validation_subjects_ids)}'

  @api.depends('validation_subjects_not_for_correction_ids')
  def _compute_validation_subjects(self):
    #for validation in self:
      self.ensure_one()
      self.validation_subjects_for_correction_ids = self.validation_subjects_ids.filtered(lambda t: t.state == '1')
      self.validation_subjects_not_for_correction_ids = self.validation_subjects_ids.filtered(lambda t: t.state != '1')

  @api.depends('validation_subjects_for_correction_ids')
  def _compute_validation_subjects_not(self):
    self.ensure_one()
    self.validation_subjects_for_correction_ids = self.validation_subjects_ids.filtered(lambda t: t.state == '1')
    self.validation_subjects_not_for_correction_ids = self.validation_subjects_ids.filtered(lambda t: t.state != '1')

  def _compute_documentation_filename(self):
    self.ensure_one()
    self.documentation_filename = '[{}][{}] {}, {}'.format(
        self.student_id.moodle_id,
        self.attempt_number,
        self.student_surname.upper() if self.student_surname is not None else 'SIN-APELLIDOS', 
        self.student_name.upper() if self.student_name is not None else 'SIN-NOMBRE')
     
  @api.depends('validation_subjects_not_for_correction_ids.is_read_only')
  def _compute_info(self):
    self.ensure_one()

    if int(self.situation) == 6:
      self.info = f'La convalidación se encuentra en estado de \'{dict(self._fields["situation"].selection).get(self.situation)}\' y no puede ser modificada'
      return
    
    if int(self.situation) == 7:
      self.info = f'El expediente que el alumno ha solicitado al Centro no existe'
      return

    if int(self.state) == 2 and self.situation == '2':
      unlocked_info = ''
      if any(val.is_read_only == False for val in self.validation_subjects_ids):
        unlocked_info = '\n¡IMPORTANTE! Alguna convalidación ha sido desbloqueada para ser modificada. Si se modifica y se graba el estudiante será notificado de manera inmediata del nuevo estado de la convalidación'
      
      self.info = 'La convalidación está en estado de \'Subsanación\' y ya ha sido notificada al estudiante.' + unlocked_info
      return
    
    self.info = f'La convalidación se encuentra en estado de \'{dict(self._fields["state"].selection).get(self.state)}\' y no puede ser modificada'

    if (self.env.user.has_group('maya_core.group_ROOT')) or \
       (self.env.user.has_group('maya_core.group_ADMIN') and int(self.state) != 14) or \
       (self.env.user.has_group('maya_core.group_MNGT_FP') and int(self.state) < 11) or \
       (self.env.user.has_group('maya_valid.group_VALID') and int(self.state) < 6):
      self.info = ''

  @api.depends('sign_data')
  def _compute_sign_info(self):
    """
    Monta la cadena que se va a mostrar con información sobre la firma
    """
    self.ensure_one()

    if self.sign_data == False:
      self.sign_info = ''
      self.sign_state = True
      return
    
    sign_data_object = json.loads(self.sign_data)
    if 'success' in sign_data_object:  
      if sign_data_object['success'] == True:
        self.sign_info = 'Firma correcta: ' + sign_data_object['CN']
        self.sign_state = True
      else:
        self.sign_info = 'Firma no válida'
        self.sign_state = False
    else:
      self.sign_state = False
  
  def download_validation_action(self):
    """
    Descarga la última versión de la documentación
    """
    self.ensure_one() # esta función sólo puede ser llamada por un único registro, no por un recordset

    # el acceso a ir.config_parameter sólo es posible desde el administrador. 
    # para que un usuario no admin (por ejemplo un convalidador) pueda acceder a descargar la documuentación
    # se utiliza la función sudo() para saltar los reglas de acceso
    validations_path = self.env['ir.config_parameter'].sudo().get_param('maya_valid.validations_path') or None
    if validations_path == None:
      _logger.error('La ruta de almacenamiento de convalidaciones no está definida')
      return

    current_sy = (self.env['maya_core.school_year'].search([('state', '=', 1)])) # curso escolar actual  

    if len(current_sy) == 0:
      raise MayaException(
          _logger, 
          'No se ha definido un curso actual',
          50, # critical
          comments = '''Es posible que no se haya marcado como actual ningún curso escolar''')
    else:
      current_school_year = current_sy[0]

    path = os.path.join(validations_path, 
          '%s_%s' % (current_school_year.date_init.year, current_school_year.date_init.year + 1), 
          self.study_abbr) 

    foldername = '[{}] {}, {}'.format(
        self.student_id.moodle_id,
        self.student_surname.upper() if self.student_surname is not None else 'SIN-APELLIDOS', 
        self.student_name.upper() if self.student_name is not None else 'SIN-NOMBRE')
      
    filename = '{}[{}][{}] {}, {}'.format(
        'UC ' if self.validation_type == COMPETENCY_VAL else '',
        self.student_id.moodle_id,
        self.attempt_number,
        self.student_surname.upper() if self.student_surname is not None else 'SIN-APELLIDOS', 
        self.student_name.upper() if self.student_name is not None else 'SIN-NOMBRE')
    
    foldername_nor = normalize('NFKD',foldername.replace(' ','_')).encode('ASCII', 'ignore').decode('utf-8')
    filename_nor = normalize('NFKD',filename.replace(' ','_')).encode('ASCII', 'ignore').decode('utf-8')

    documentation_filename = f'{path}/{foldername_nor}/{filename_nor}.zip'

    try:
      with open(documentation_filename, 'rb') as f:
        file_bytes = f.read()
        encode_data = base64.b64encode(file_bytes)
    except Exception as e:
      _logger.error('Error descargando el fichero:' + str(e))
      return {}
      
    self.documentation = encode_data

    return {
      'type': 'ir.actions.act_url',
      'url': 'web/content?model=maya_valid.validation&id=%s&field=documentation&filename=%s.zip&download=true' % 
        (self.id, filename_nor.replace(' ','%20'))
    }
  
  def download_validation_claim_action(self):
    """
    Descarga la reclamación de la documentación
    """
    self.ensure_one() # esta función sólo puede ser llamada por un único registro, no por un recordset

    # el acceso a ir.config_parameter sólo es posible desde el administrador. 
    # para que un usuario no admin (por ejemplo un convalidador) pueda acceder a descargar la documuentación
    # se utiliza la función sudo() para saltar los reglas de acceso
    validations_path = self.env['ir.config_parameter'].sudo().get_param('maya_valid.validations_path') or None
    if validations_path == None:
      _logger.error('La ruta de almacenamiento de convalidaciones no está definida')
      return

    current_sy = (self.env['maya_core.school_year'].search([('state', '=', 1)])) # curso escolar actual  

    if len(current_sy) == 0:
      raise MayaException(
          _logger, 
          'No se ha definido un curso actual',
          50, # critical
          comments = '''Es posible que no se haya marcado como actual ningún curso escolar''')
    else:
      current_school_year = current_sy[0]

    path = os.path.join(validations_path, 
          '%s_%s' % (current_school_year.date_init.year, current_school_year.date_init.year + 1), 
          self.study_abbr) 

    foldername = '[{}] {}, {}'.format(
        self.student_id.moodle_id,
        self.student_surname.upper() if self.student_surname is not None else 'SIN-APELLIDOS', 
        self.student_name.upper() if self.student_name is not None else 'SIN-NOMBRE')
      
    filename = 'RECLAMACION [{}] {}, {}'.format(
        self.student_id.moodle_id,
        self.student_surname.upper() if self.student_surname is not None else 'SIN-APELLIDOS', 
        self.student_name.upper() if self.student_name is not None else 'SIN-NOMBRE')
    
    foldername_nor = normalize('NFKD',foldername.replace(' ','_')).encode('ASCII', 'ignore').decode('utf-8')
    filename_nor = normalize('NFKD',filename.replace(' ','_')).encode('ASCII', 'ignore').decode('utf-8')

    documentation_filename = f'{path}/{foldername_nor}/{filename_nor}.zip'

    try:
      with open(documentation_filename, 'rb') as f:
        file_bytes = f.read()
        encode_data = base64.b64encode(file_bytes)
    except Exception as e:
      _logger.error('Error descargando el fichero:' + str(e))
      return {}
  
    self.documentation = encode_data

    return {
      'type': 'ir.actions.act_url',
      'url': 'web/content?model=maya_valid.validation&id=%s&field=documentation&filename=%s.zip&download=true' % 
        (self.id, filename_nor.replace(' ','%20'))
    }

  @api.depends('validation_subjects_ids')
  def _compute_state(self):
    for record in self:  
      all_noprocess = all(val.state == '0' for val in record.validation_subjects_ids)
      any_noprocess = any(val.state == '0' for val in record.validation_subjects_ids)
      any_correction = any(val.state == '1' for val in record.validation_subjects_ids)
      any_higher_level = any(val.state == '2' for val in record.validation_subjects_ids)
      any_resolved = any(val.state == '3' for val in record.validation_subjects_ids)
      all_resolved = all(val.state == '3' for val in record.validation_subjects_ids)
      all_reviewed = all(val.state == '4' for val in record.validation_subjects_ids)
      any_reviewed = any(val.state == '4' for val in record.validation_subjects_ids)
      all_reviewed_claim = all(val.state == '9' for val in record.validation_subjects_ids)
      any_reviewed_claim = any(val.state == '9' for val in record.validation_subjects_ids)
      any_finished = any(val.state == '6' for val in record.validation_subjects_ids)
      all_finished = all(val.state == '6' for val in record.validation_subjects_ids)
      all_closed = all(val.state == '7' for val in record.validation_subjects_ids) or (all_finished and record.state == '15')

      if record.situation == '6': # se está a la espera de que secretaria genere el expediente
        continue

      if record.situation == '7' and not any_noprocess: # el expediente solicitado no existe y no hay ninguna en no procesada
        record.situation = '0'

      # En cuanto alguna esté procesada (resuelta o subsanacion) ya se reinicia la situación
      if record.situation == '8' and (any_resolved or any_correction): 
        record.situation = '0'

      # si está ya notificado al estudiante o estaba en subsanación o finalizada o instancia superior
      if record.situation == '2':
        # si hay alguna subsanación/instancia superior es que es subsanación/instancia superior
        if any_correction and any_higher_level:
          record.state = '4'
          continue
        
        # si hay alguna subsanación es que es subsanación
        if any_correction:
          record.state = '2'
          continue
      
        # si hay alguna instancia superior es que es instancia superior
        if any_higher_level:
          record.state = '3'
          continue

      # con notificación enviada se han realizado cambios
      if record.situation == '5':
        # alguno se ha pasado a no procesada (solo lo puede hacer admin)
        if any_noprocess:
          record.state = '1' # En proceso
          return

        # si hay instancias superiores y subsanaciones -> subsanación/instancia superior
        if any_higher_level and any_correction:
          record.state = '4'
          continue

        # si hay alguna en instancia superior -> instancia superior
        if any_higher_level:
          record.state = '3'
          continue
    
        # si hay al menos una subsanación  -> subsanacion
        if any_correction:
          record.state = '2'
          continue
      
        if all_resolved:
          record.state = '5' # Resuelta
          continue
      
        """  if record.situation == '3':
        record.state = '2'
        continue """

      if record.situation == '3' and not any_correction:
        record.situation = '0'
        continue   
      elif record.situation == '3':
        record.state = '2'
        continue
      else:
        record.situation = '0'

      # si todas sin procesar -> sin procesar
      if all_noprocess:
        record.state = '0'
        continue

      # si todas resueltas -> resuelta
      if all_resolved:
        record.state = '5'
        record.correction_reason = False
        record.correction_date = False
        continue
  
      # si todas revisada -> revisada
      if all_reviewed:
        record.state = '8'
        # podria ser revisada sin ser resuelta (resuelve un revisor)
        record.correction_reason = False
        record.correction_date = False
        continue
      
      if all_closed:
        record.state = '15'
        continue

      # si todas finalizadas -> finalizada
      if all_finished:
        record.state = '13'
        continue

      # si todas han sido revisada tras la reclamación
      if all_reviewed_claim:
        record.state = '17'
        continue

      # si hay instancias superiores y subsanaciones -> subsanación/instancia superior
      if any_higher_level and any_correction and record.situation != '3':
        record.state = '4'
        record.situation = '1'
        continue
      elif any_higher_level and any_correction:
        record.state = '4'
        continue

      # si hay alguna en instancia superior y no hay ninguna pendiente -> instancia superior
      if any_higher_level and not any_noprocess:
        record.state = '3'
        continue
      
      # si hay al menos una subsanación y no hay ninguna pendiente -> subsanacion
      if any_correction and not any_noprocess and record.situation != '3':
        record.state = '2'
        record.situation = '1'
        continue
      elif any_correction and not any_noprocess:
        record.state = '2'    
        continue

      # si hay alguna sin procesar y otras ya resueltas o pendientes de subsanación o a instancias superiores -> en proceso
      if any_noprocess and (any_resolved or any_correction or any_higher_level):
        record.state = '1'
        continue

      # si hay alguna sin revisar y otras ya revisadas -> en proceso de revision (parcial)
      if any_resolved and any_reviewed and any_higher_level:
        record.state = '7'
        continue

      # si sólo hay revisadas y instancias superiores -> Revisada parcialmente
      if any_reviewed and any_higher_level:
        record.state = '9'
        continue

      # si hay alguna sin revisar y otras ya revisadas -> en proceso de revision
      if any_resolved and any_reviewed:
        record.state = '6'
        continue

      # si hay alguna sin finalizar y otras ya finalizadas -> en proceso de finalización (parcial)
      if any_finished and any_reviewed and any_higher_level:
        record.state = '10'
        continue

      # si sólo hay finalizadas e instancias superiores -> Finalizada parcialmente
      if any_finished and any_higher_level:
        record.state = '11'
        continue

      # si hay alguna sin finalizar y otras ya finalizadas -> en proceso de finalización
      if any_finished and any_reviewed:
        record.state = '12'
        continue

  def _compute_is_state_read_only(self):
    for record in self:
      record.is_state_read_only = False

      if int(record.state) >= 6 and \
        self.env.user.has_group('maya_valid.group_VALID') and \
        not self.env.user.has_group('maya_core.group_MNGT_FP'):
          record.is_state_read_only = True

      if int(record.state) == 14 and \
        self.env.user.has_group('maya_core.group_ADMIN'):
          record.is_state_read_only = True

      if int(record.state) >= 13 and \
        self.env.user.has_group('maya_core.group_MNGT_FP'):
          record.is_state_read_only = True
  
  def validation_to_finished(self):
    """
    Cambia el estado de una convalidación a finalizada y su situación a fuera de plazo
    La convalidación tiene que estar en estado de subsanación y no tener módulos añadidos, es decir, que esté en una 
    subsanación por formato, no por falta de documentación
    """
    if self.env.is_admin() == False:
      raise AccessDenied('Sólo el administrador puede cambiar el estado de la convalidación')
    
    self.ensure_one() # esta función sólo puede ser llamada por un único registro, no por un recordset

    if (int(self.state) != 2 and int(self.situation) != 4) or len(self.validation_subjects_ids) != 0:
      raise AccessDenied('Sólo se pueden finalizar convalidaciones en estado de subsanación, fuera de plazo y sin módulos')

    self.situation = '4' #  fuera de plazo
    self.state = '13' # finalizada
    