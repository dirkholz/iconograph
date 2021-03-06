#!/usr/bin/python3

import argparse
import fetcher
import json
import lib
import os
import socket
import subprocess
import time
import update_grub
from ws4py.client import threadedclient


parser = argparse.ArgumentParser(description='iconograph fetcher')
parser.add_argument(
    '--boot-dir',
    dest='boot_dir',
    action='store',
    required=True)
parser.add_argument(
    '--config',
    dest='config',
    action='store',
    default='/etc/iconograph.json')
parser.add_argument(
    '--ca-cert',
    dest='ca_cert',
    action='store',
    required=True)
parser.add_argument(
    '--https-ca-cert',
    dest='https_ca_cert',
    action='store',
    required=True)
parser.add_argument(
    '--https-client-cert',
    dest='https_client_cert',
    action='store',
    required=True)
parser.add_argument(
    '--https-client-key',
    dest='https_client_key',
    action='store',
    required=True)
parser.add_argument(
    '--image-dir',
    dest='image_dir',
    action='store',
    required=True)
parser.add_argument(
    '--server',
    dest='server',
    action='store',
    required=True)
FLAGS = parser.parse_args()


class Client(threadedclient.WebSocketClient):

  def __init__(self, config_path, *args, **kwargs):
    super().__init__(*args, **kwargs)
    with open(config_path, 'r') as fh:
      self._config = json.load(fh)

  def Loop(self):
    self.daemon = True
    self.connect()
    self._UpdateManifest()
    while True:
      self._SendReport()
      time.sleep(5.0)

  def _SendReport(self, status=None):
    report = {
      'hostname': socket.gethostname(),
      'uptime_seconds': self._Uptime(),
      'next_timestamp': self._NextTimestamp(),
      'next_volume_id': lib.GetVolumeID('/isodevice/iconograph/current'),
    }
    if status:
      report['status'] = status
    report.update(self._config)
    self.send(json.dumps({
      'type': 'report',
      'data': report,
    }))

  def _Uptime(self):
    with open('/proc/uptime', 'r') as fh:
      return int(float(fh.readline().split(' ', 1)[0]))

  def _NextTimestamp(self):
    next_image = lib.GetCurrentImage()
    return int(next_image.split('.', 1)[0])

  def _OnImageTypes(self, data):
    assert self._config['image_type'] in data['image_types']

  def _OnNewManifest(self, data):
    if data['image_type'] != self._config['image_type']:
      return
    self._UpdateManifest()

  def _GetFetcher(self):
    return fetcher.Fetcher(
        'https://%s/image/%s' % (FLAGS.server, self._config['image_type']),
        FLAGS.ca_cert,
        FLAGS.image_dir,
        FLAGS.https_ca_cert,
        FLAGS.https_client_cert,
        FLAGS.https_client_key)

  def _UpdateGrub(self):
    update = update_grub.GrubUpdater(
        FLAGS.image_dir,
        FLAGS.boot_dir)
    update.Update()

  def _UpdateManifest(self):
    fetch = self._GetFetcher()
    fetch.Fetch()
    fetch.DeleteOldImages(skip={'%d.iso' % self._config['timestamp']})
    self._UpdateGrub()

  def _OnCommand(self, data):
    if data['command'] == 'reboot':
      self._OnReboot(data)

  def _OnReboot(self, data):
    if 'timestamp' in data:
      fetch = self._GetFetcher()
      fetch.Fetch(data['timestamp'])
      self._UpdateGrub()
      self._SendReport('Rebooting into %d...' % data['timestamp'])
    else:
      self._SendReport('Rebooting...')

    subprocess.check_call(['reboot'])

  def received_message(self, msg):
    parsed = json.loads(msg.data.decode('utf8'))
    if parsed['type'] == 'image_types':
      self._OnImageTypes(parsed['data'])
    elif parsed['type'] == 'new_manifest':
      self._OnNewManifest(parsed['data'])
    elif parsed['type'] == 'command':
      self._OnCommand(parsed['data'])


def main():
  ssl_options = {
    'keyfile': FLAGS.https_client_key,
    'certfile': FLAGS.https_client_cert,
    'ca_certs': FLAGS.https_ca_cert,
  }
  client = Client(
      FLAGS.config,
      'wss://%s/ws/slave' % FLAGS.server,
      protocols=['iconograph-slave'],
      ssl_options=ssl_options)
  client.Loop()


if __name__ == '__main__':
  main()
