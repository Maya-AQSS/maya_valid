from odoo import models

class ValidationReport(models.AbstractModel):
  _name = 'report.maya_valid.report_validations'
  _description = 'Informe de convalidaciones'

  def _get_report_values(self, docids, data=None):
    """
    Prepara los valores que se pasarán al template QWeb
    """
    docs = self.env['maya_valid.validation'].browse(docids)
    
    return {
      'doc_ids': docids,
      'doc_model': 'maya_valid.validation',
      'docs': docs,
      'course': data.get('course') if data else '',
    }