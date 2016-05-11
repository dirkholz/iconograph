#!/usr/bin/python3

import lib
import os
import string
import tempfile


class GrubUpdater(object):

  _HOTKEYS = string.digits + string.ascii_letters

  def __init__(self, image_dir, boot_dir):
    self._image_dir = image_dir
    self._boot_dir = boot_dir

    assert self._image_dir.startswith(self._boot_dir)

    self._image_path = '/' + os.path.relpath(self._image_dir, self._boot_dir)

  def Update(self):
    grub_dir = os.path.join(self._boot_dir, 'grub')

    with tempfile.NamedTemporaryFile('w', dir=grub_dir, delete=False) as fh:
      try:
        current = lib.GetCurrentImage(self._image_dir)

        fh.write("""
set timeout=5
set default="%(default_image_filename)s (%(default_volume_id)s)"
""" % {
          'default_image_filename': current,
          'default_volume_id': lib.GetVolumeID(os.path.join(self._image_dir, current)),
        })

        files = []
        for filename in os.listdir(self._image_dir):
          if not filename.endswith('.iso'):
            continue
          files.append(filename)

        for i, filename in enumerate(sorted(files, reverse=True)):
          fh.write("""
menuentry "%(image_filename)s (%(volume_id)s)" --hotkey=%(hotkey)s {
  search --no-floppy --file --set=root %(image_path)s/%(image_filename)s
  iso_path="%(image_path)s/%(image_filename)s"
  export iso_path
  loopback loop "%(image_path)s/%(image_filename)s"
  set root=(loop)
  configfile /boot/grub/loopback.cfg
}
""" % {
            'image_filename': filename,
            'image_path': self._image_path,
            'hotkey': self._HOTKEYS[i],
            'volume_id': lib.GetVolumeID(os.path.join(self._image_dir, filename)),
          })

        fh.flush()
        os.rename(fh.name, os.path.join(grub_dir, 'grub.cfg'))
      except:
        os.unlink(fh.name)
        raise
