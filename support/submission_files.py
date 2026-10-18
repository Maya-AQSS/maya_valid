# -*- coding: utf-8 -*-
"""
Ficheros de las entregas de convalidaciones: guardar el zip, descomprimirlo y normalizar los
nombres. No depende de Odoo.
"""
import io
import os
import shutil
import zipfile
from unicodedata import normalize

# carpetas que añaden algunos sistemas operativos al comprimir y que no son de la entrega
JUNK_ENTRIES = ('__MACOSX', '.DS_Store', 'Thumbs.db', 'desktop.ini')

# límites contra zips maliciosos o erróneos (zip bomb)
MAX_UNZIPPED_BYTES = 500 * 1024 * 1024
MAX_ENTRIES = 1000


class BadSubmissionZip(Exception):
  """ El fichero no se puede descomprimir: no es un zip, está cifrado o supera los límites """


def normalize_name(name):
  """
  Nombre de fichero o carpeta sin espacios ni caracteres no ASCII, como hacía el proceso
  antiguo: 'Anexo Ñandú.pdf' -> 'Anexo_Nandu.pdf'
  """
  return normalize('NFKD', name.replace(' ', '_')).encode('ASCII', 'ignore').decode('ASCII')


def is_zip(data):
  return zipfile.is_zipfile(io.BytesIO(data))


def save_and_extract(data, folder, name):
  """
  Guarda el zip como <folder>/<name>.zip y lo descomprime en <folder>/<name>/. Si ya había
  algo (un intento anterior a medias), se sustituye.

  Después de descomprimir:
    - se borran las carpetas y ficheros basura (__MACOSX...)
    - si todo está dentro de una única carpeta, se sube su contenido un nivel
    - se normalizan los nombres (normalize_name) y se pasan a mayúsculas

  :return: (ruta del zip, ruta de la carpeta descomprimida)
  """
  os.makedirs(folder, exist_ok = True)
  zip_path = os.path.join(folder, name + '.zip')
  extract_path = os.path.join(folder, name)

  with open(zip_path, 'wb') as f:
    f.write(data)

  if os.path.exists(extract_path):
    shutil.rmtree(extract_path)
  os.makedirs(extract_path)

  try:
    with zipfile.ZipFile(zip_path) as zf:
      infos = zf.infolist()
      if len(infos) > MAX_ENTRIES:
        raise BadSubmissionZip('El zip tiene demasiados ficheros (%d).' % len(infos))
      if sum(i.file_size for i in infos) > MAX_UNZIPPED_BYTES:
        raise BadSubmissionZip('El zip descomprimido ocupa demasiado.')
      if any(i.flag_bits & 0x1 for i in infos):
        raise BadSubmissionZip('El zip está protegido con contraseña.')
      # extractall ya descarta las rutas absolutas y los '..' de los nombres
      zf.extractall(extract_path)
  except (zipfile.BadZipFile, zipfile.LargeZipFile, NotImplementedError, OSError, EOFError) as e:
    raise BadSubmissionZip('No se puede descomprimir el zip: %s' % e)

  _remove_junk(extract_path)
  _flatten_single_folder(extract_path)
  _normalize_tree(extract_path)
  return zip_path, extract_path


def _remove_junk(path):
  for root, dirs, files in os.walk(path):
    for d in [d for d in dirs if d in JUNK_ENTRIES]:
      shutil.rmtree(os.path.join(root, d))
      dirs.remove(d)
    for f in files:
      if f in JUNK_ENTRIES or f.startswith('._'):
        os.remove(os.path.join(root, f))


def _flatten_single_folder(path):
  """ Si el alumno comprimió una carpeta con todo dentro, su contenido sube a path """
  entries = os.listdir(path)
  if len(entries) != 1 or not os.path.isdir(os.path.join(path, entries[0])):
    return
  inner = os.path.join(path, entries[0])
  tmp = inner + '.__tmp__'
  os.rename(inner, tmp)
  for entry in os.listdir(tmp):
    os.rename(os.path.join(tmp, entry), os.path.join(path, entry))
  os.rmdir(tmp)


def _normalize_tree(path):
  """ Normaliza y pasa a mayúsculas los nombres, de abajo arriba para no romper las rutas """
  for root, dirs, files in os.walk(path, topdown = False):
    for name in dirs + files:
      new_name = normalize_name(name).upper()
      if new_name == name:
        continue
      new_path = _free_path(os.path.join(root, new_name))
      os.rename(os.path.join(root, name), new_path)


def _free_path(path):
  """ path, o path con un sufijo (_2, _3...) si ya existe """
  if not os.path.exists(path):
    return path
  base, ext = os.path.splitext(path)
  n = 2
  while os.path.exists('%s_%d%s' % (base, n, ext)):
    n += 1
  return '%s_%d%s' % (base, n, ext)
