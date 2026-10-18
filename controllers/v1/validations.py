# -*- coding: utf-8 -*-
"""
Endpoint v1 para sincronizar las entregas de convalidaciones de Moodle. Lo llama n8n.

POST /api/v1/validations/<type>/sync        type: studies | competency
Authorization: Bearer <api_key>
Content-Type: application/json

Body (todos los campos son opcionales):
{
    "kind":  "request",      # request (solicitud, por defecto) | claim (reclamación)
    "study": "DAW"           # solo las tareas de ese estudio
}

Respuesta:
{
    "success": true,
    "type": "studies", "kind": "request",
    "tasks":  [{"task_id": 359859, "study": "DAW", "received": 10, "created": 2, "updated": 1,
                "unchanged": 7, "unmatched": 0}, ...],
    "totals": {"received": 10, "created": 2, ...}
}
Un fallo en una tarea aparece en su entrada como "error" y no detiene las demás.
"""
import json
import logging

from odoo import http
from odoo.exceptions import UserError
from odoo.http import request

from odoo.addons.maya_core.controllers.api_auth import ApiBaseController, error_response, json_response
from ...models.validation import STUDIES_VAL, COMPETENCY_VAL
from ...models.submission import REQUEST, CLAIM

_logger = logging.getLogger(__name__)

VALIDATION_TYPES = {'studies': STUDIES_VAL, 'competency': COMPETENCY_VAL}
KINDS = (REQUEST, CLAIM)


class ValidationsApiController(ApiBaseController):

  @http.route(
      '/api/v1/validations/<string:validation_type>/sync',
      type='http',
      auth='none',        # autenticación gestionada manualmente vía API key
      methods=['POST'],
      csrf=False,
      save_session=False,
  )
  def sync_submissions(self, validation_type, **kwargs):
    app_user, err = self._authenticate(
        require_human_user=False,
        required_group='maya_valid.group_valid_integration',
    )
    if err:
      return err

    if validation_type not in VALIDATION_TYPES:
      return error_response('El tipo de convalidación debe ser studies o competency.', 'INVALID_TYPE', 404)

    # sin Content-Type JSON, werkzeug consume el cuerpo como formulario y se ignoraría en silencio
    if request.httprequest.content_length and request.httprequest.mimetype != 'application/json':
      return error_response('El cuerpo debe enviarse con Content-Type: application/json.', 'UNSUPPORTED_MEDIA_TYPE', 415)

    try:
      body = json.loads(request.httprequest.data or '{}')
    except json.JSONDecodeError:
      return error_response('El cuerpo de la petición no es JSON válido.', 'INVALID_JSON', 400)
    if not isinstance(body, dict):
      return error_response('El cuerpo de la petición debe ser un objeto JSON.', 'INVALID_JSON', 400)

    kind = body.get('kind') or REQUEST
    if kind not in KINDS:
      return error_response('kind debe ser request o claim.', 'INVALID_PARAM', 400)
    study = body.get('study') or None
    if study is not None and not isinstance(study, str):
      return error_response('study debe ser la abreviatura de un estudio.', 'INVALID_PARAM', 400)

    try:
      result = request.env['maya_moodle.submission'].with_user(app_user).sudo().sync_validations(
          VALIDATION_TYPES[validation_type], kind=kind, study_abbr=study)
    except UserError as e:
      # configuración incompleta (gateway, usuario de servicio...)
      _logger.error('Sincronización de entregas de convalidaciones: %s', e)
      return error_response(str(e.args[0]) if e.args else str(e), 'CONFIGURATION_ERROR', 503)

    return json_response({'success': True, 'type': validation_type, 'kind': kind, **result})
