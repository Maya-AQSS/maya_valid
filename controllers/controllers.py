# -*- coding: utf-8 -*-
from odoo import http
from odoo.http import request

class ValidationController(http.Controller):

  @http.route('/validation/validation_banner/', auth='user', type='jsonrpc')
  def get_banner_data(self, **kw):
    """
    Ruta para mostar en banner en las convalidaciones
    No se permite la llamada directa desde el navegador ya que el tipo es json, no http
    """
    user =  request.env.user
    is_coord = is_validator = is_root = is_admin = False
     
    if user.has_group('maya_valid.group_VALID'):
      is_validator = True

    if user.has_group('maya_core.group_ADMIN'):
      is_admin = True

    if user.has_group('maya_core.group_MNGT_FP'):
      is_coord = True
    
    if user.has_group('maya_core.group_ROOT'):
      is_root = True

    if is_root:
      studies = [study.abbr for study in request.env['maya_core.study'].search([])]
    else:
      studies = [rol.study_id.abbr for rol in user.maya_employee_id.roles_ids if rol.rol == 'CONV' and rol.study_id]

    if len(studies)>0:
      user_num_valid = request.env['maya_valid.validation_subject'].search_count([('validation_id.study_id.abbr', 'in', studies)])
      user_num_resolved = request.env['maya_valid.validation_subject'].search_count([('validation_id.study_id.abbr', 'in', studies),
                                                                               ('state','=','3')])
      user_num_for_correction = request.env['maya_valid.validation_subject'].search_count([('validation_id.study_id.abbr', 'in', studies),
                                                                                     ('state','=','1')])  
      user_num_higher_level = request.env['maya_valid.validation_subject'].search_count([('validation_id.study_id.abbr', 'in', studies),
                                                                                     ('state','=','2')])
      user_in_process = request.env['maya_valid.validation_subject'].search_count([('validation_id.study_id.abbr', 'in', studies),
                                                                                     ('state','=','0')])  
    else:
      user_num_valid = user_num_resolved = user_num_for_correction = user_num_higher_level = user_in_process = 0

    num_valid = request.env['maya_valid.validation_subject'].search_count([])
    num_resolved = request.env['maya_valid.validation_subject'].search_count([('state','>=','3')])
    num_reviewed = request.env['maya_valid.validation_subject'].search_count([('state','>=','4'),('state','!=','5')])
    num_higher_level = request.env['maya_valid.validation_subject'].search_count([('state','=','2')])
    # el dominio se define mediante notación polaca
    num_finished = request.env['maya_valid.validation_subject'].search_count(['|', ('state','=','6'), ('state','=','7')])
    num_rejected = request.env['maya_valid.validation_subject'].search_count(['&', ('state','>=','3'), ('accepted','=','2')])

    qweb = request.env['ir.qweb']

    return {
      # hay que prefijar con el nombre del módulo, aunque el id del template no lo lleva
      'html': qweb._render('maya_valid.validation_banner_template', {
              'is_root': is_root,
              'num_valid': num_valid,
              # es validador
              'is_validator': is_validator,
              'user_num_valid': user_num_valid,
              'user_num_resolved': user_num_resolved,
              'user_num_for_correction': user_num_for_correction,
              'user_num_higher_level': user_num_higher_level,
              'user_in_process': user_in_process,
              # es revisor
              'is_coord': is_coord,
              'num_resolved': num_resolved,
              'num_reviewed_in_process': num_resolved - num_reviewed,
              # es secretaría
              'is_admin': is_admin,
              'num_finished': num_finished,
              'num_reviewed': num_reviewed,
              'num_finished_in_process': num_reviewed - num_finished,
              'num_higher_level': num_higher_level,
              'num_rejected': num_rejected 
            })
          } 