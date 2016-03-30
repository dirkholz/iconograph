#!/usr/bin/python3

import argparse
import os
import shutil
import subprocess
import sys
import tempfile


parser = argparse.ArgumentParser(description='iconograph build_image')
parser.add_argument(
    '--arch',
    dest='arch',
    action='store',
    default='amd64')
parser.add_argument(
    '--archive',
    dest='archive',
    action='store',
    default='http://archive.ubuntu.com/ubuntu')
parser.add_argument(
    '--dest-iso',
    dest='dest_iso',
    action='store',
    required=True)
parser.add_argument(
    '--release',
    dest='release',
    action='store',
    required=True)
parser.add_argument(
    '--shell',
    dest='shell',
    action='store_true',
    default=False)
parser.add_argument(
    '--source-iso',
    dest='source_iso',
    action='store',
    required=True)
FLAGS = parser.parse_args()


class ImageBuilder(object):

  _BASE_PACKAGES = [
    'debconf',
    'devscripts',
    'dialog',
    'git',
    'gnupg',
    'isc-dhcp-client',
    'locales',
    'nano',
    'net-tools',
    'iputils-ping',
    'openssh-server',
    'python3-openssl',
    'sudo',
    'user-setup',
    'wget',
  ]

  def __init__(self, source_iso, dest_iso, archive, arch, release):
    self._source_iso = source_iso
    self._dest_iso = dest_iso
    self._archive = archive
    self._arch = arch
    self._release = release

    self._ico_server_path = os.path.dirname(sys.argv[0])

    self._umount = []
    self._rmtree = []

  def _Exec(self, *args):
    print('+', args)
    subprocess.check_call(args)

  def _ExecChroot(self, chroot_path, *args):
    self._Exec('chroot', chroot_path, *args)

  def _Debootstrap(self, root):
    path = os.path.join(root, 'chroot')
    os.mkdir(path)
    self._Exec(
        'debootstrap',
        '--variant=buildd',
        '--arch', self._arch,
        self._release,
        path,
        self._archive)
    return path

  def _CreateUnion(self, root):
    iso_path = os.path.join(root, 'iso')
    os.mkdir(iso_path)
    self._Exec(
        'mount',
        '--options', 'loop,ro',
        self._source_iso,
        iso_path)
    self._umount.append(iso_path)

    tmpfs_path = os.path.join(root, 'tmpfs')
    os.mkdir(tmpfs_path)
    self._Exec(
        'mount',
        '--types', 'tmpfs',
        'none',
        tmpfs_path)
    self._umount.append(tmpfs_path)

    upper_path = os.path.join(tmpfs_path, 'upper')
    os.mkdir(upper_path)

    work_path = os.path.join(tmpfs_path, 'work')
    os.mkdir(work_path)

    union_path = os.path.join(root, 'union')
    os.mkdir(union_path)
    self._Exec(
        'mount', 
        '--types', 'overlayfs',
        '--options', 'lowerdir=%s,upperdir=%s,workdir=%s' % (iso_path, upper_path, work_path),
        'none',
        union_path)
    self._umount.append(union_path)

    return union_path

  def _InstallPackages(self, chroot_path):
    self._ExecChroot(
        chroot_path,
        'apt-get',
        'install',
        '--assume-yes',
        *self._BASE_PACKAGES)
    self._ExecChroot(
        chroot_path,
        'apt-get',
        'clean')

  def _InstallIconograph(self, chroot_path):
    self._ExecChroot(
        chroot_path,
        'git',
        'clone',
        'https://github.com/robot-tools/iconograph.git')

  def _Squash(self, chroot_path, union_path):
    self._Exec(
        'mksquashfs',
        chroot_path,
        os.path.join(union_path, 'casper', 'filesystem.squashfs'),
        '-noappend')

  def _FixGrub(self, union_path):
    shutil.copyfile(
        os.path.join(self._ico_server_path, 'iso_files', 'grub.cfg'),
        os.path.join(union_path, 'boot', 'grub', 'loopback.cfg'))

  def _CreateISO(self, union_path):
    self._Exec(
        'grub-mkrescue',
        '--output=%s' % self._dest_iso,
        union_path)

  def _BuildImage(self):
    root = tempfile.mkdtemp()
    self._rmtree.append(root)

    print('Building image in:', root)

    chroot_path = self._Debootstrap(root)
    union_path = self._CreateUnion(root)
    self._InstallPackages(chroot_path)
    self._InstallIconograph(chroot_path)
    if FLAGS.shell:
      self._Exec('bash')
    self._Squash(chroot_path, union_path)
    self._FixGrub(union_path)
    self._CreateISO(union_path)

  def BuildImage(self):
    try:
      self._BuildImage()
    finally:
      pass
      for path in self._umount:
        self._Exec('umount', path)
      for path in self._rmtree:
        shutil.rmtree(path)


def main():
  builder = ImageBuilder(
      FLAGS.source_iso,
      FLAGS.dest_iso,
      FLAGS.archive,
      FLAGS.arch,
      FLAGS.release)
  builder.BuildImage()


if __name__ == '__main__':
  main()