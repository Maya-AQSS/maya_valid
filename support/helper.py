# -*- coding: utf-8 -*-
import hashlib

import logging

from ...maya_core.support.maya_logger.exceptions import MayaException

_logger = logging.getLogger(__name__)

# basado en https://stackoverflow.com/questions/22058048/hashing-a-file-in-python
def get_sha1_file(filename: str) -> str:
  """
  Devuelve el sha1 de un fichero

  filename: path completo del fichero
  """
  # BUF_SIZE is totally arbitrary, change for your app!
  BUF_SIZE = 65536  # lets read stuff in 64kb chunks!

  sha1 = hashlib.sha1()

  try:
    with open(filename, 'rb') as f:
      while True:
          data = f.read(BUF_SIZE)
          if not data:
              break

          sha1.update(data)
  except Exception:
      raise MayaException(
          _logger, 
          f'No se encuentra el fichero {filename}',
          50, # critical
          comments = '''Es posible que no se haya incorporado el fichero del que se busca el SHA1''')

  return sha1.hexdigest()

def create_HTML_list_from_list(items: list, title: str = '', ident: bool = True) -> str:
  """
  Devuelve una lista HTML (<ul>) a partir de una lista de cadenas.
  Se utiliza en los mensajes que se envían al alumnado a través de Moodle

  items: elementos de la lista
  title: texto que se muestra en un párrafo antes de la lista
  ident: si es True la lista se muestra con sangría
  """
  style = ' style="padding-left: 1rem"' if ident else ''
  title_html = f'<p>{title}</p>' if title else ''
  items_html = ''.join(f'<li>{item}</li>' for item in items)

  return f'{title_html}<ul{style}>{items_html}</ul>'
