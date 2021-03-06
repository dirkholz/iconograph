# Iconograph

Iconograph ("icon") is a system for building and deploying Ubuntu system images.
It allows you to distribute your software intended to run on real hardware or
inside a container as a single unit with its system dependencies, and to roll
forward and backward in a secure, repeatable, staged manner.

## Overview

```
+-------------------------------------------------------------+
| Physical disk                                               |
| +-----------------------------------------+ +-------------+ |
| | /boot                                   | | /persistent | |
| | +-----------------+ +-----------------+ | |             | |
| | | 1459629471.iso  | | 1459629717.iso  | | |             | |
| | |                 | |                 | | |             | |
| | | kernel          | | kernel          | | |             | |
| | | initrd          | | initrd          | | |             | |
| | |                 | |                 | | |             | |
| | | +-------------+ | | +-------------+ | | |             | |
| | | | squashfs    | | | | squashfs    | | | |             | |
| | | | / (root) fs | | | | / (root) fs | | | |             | |
| | | +-------------+ | | +-------------+ | | |             | |
| | +-----------------+ +-----------------+ | |             | |
| +-----------------------------------------+ +-------------+ |
+-------------------------------------------------------------+
```

Icon supports multiple image options at boot time by building Live CD-style ISO
images. It writes multiple ISO images to a /boot partition, and uses grub to
select between them at boot time (with hotkeys for headless selection). A second
grub instance runs inside the ISO to allow further customization (e.g. running
and upgrading memtest86).

Images utilize a tmpfs overlay filesystem, so by default filesystem changes
are discarded on reboot or upgrade. An optional /persistent filesystem allows
data storage across reboots and upgrades/downgrades.

Images optionally self-upgrade by fetching new images from an HTTP(S) source
and updating the configuration of the outer grub instance. This removes the
need for a separate OS instance to perform upgrades (and avoids figuring out
how to upgrade that instance).

## Setup

```bash
sudo apt-get install --assume-yes git grub-pc xorriso squashfs-tools openssl python3-openssl debootstrap
git clone https://github.com/robot-tools/iconograph.git
cd iconograph
```

## Image creation

### Image composition

Icon creates images by merging the kernel and boot system of a desktop live CD
with a server/custom filesystem. You'll need to download the desktop live CD
ISO for the version that you're building. You can get them [here](http://mirror.pnl.gov/releases/).

### Serving

Images are fetched via HTTP. You should write images to a directory accessible
via HTTP. Install apache2 if need be.

### Simple image build

build_image.py will call debootstrap, which will fetch packages from Ubuntu
servers. You may want to
[set up caching](https://medium.com/where-the-flamingcow-roams/apt-caching-for-debootstrap-bac499deebd5#.dvevbcc9z)
to make this process fast on subsequent runs.

```bash
# Must run as sudo to mount/umount images, tmpfs, and overlayfs
sudo server/build_image.py --image-dir=/output/path --release=trusty --source-iso=path/to/ubuntu-14.04.4-desktop-amd64.iso
```

## Modules

Modules are scripts that run after the chroot has been created. They can install
packages, do configuration, etc. Icon has several stock modules, but you can
also create your own using them as examples. You can pass multiple --module
flags to build_image.py as long as the modules are compatible with each other.

Stock modules:

### autoimage.py

Build an image that will partition, mkfs, and install an image from a different
URL onto a target system. Used to create install USB drives, PXE boot, etc.
Use the build_image.py flag:

```bash
--module="server/modules/autoimage.py --base-url=http://yourhost/ --ca-cert=/path/to/signing/cert.pem --device=/dev/sdx --persistent-percent=50"
```

`--device` specifies the device to partition and install to on the target
system.

Optional flags:

`--persistent-percent`, if non-zero, specifies the percent of the target
device to allocate to a LABEL=PERSISTENT filesystem. If the inner image uses
persistent.py, this filesystem will be automatically mounted.

`--https-ca-cert` specifies a local path to a PEM-encoded certificate to
validate the HTTPS image server cert against. This differs from `--ca-cert`,
which is used to validate the manifest.json signature.

`--https-client-cert` and `--https-client-key` are used together to specify
local paths to a PEM-encoded certificate and key pair that will be provided
to the server over HTTPS. This can be used to limit image availability.

### certclient.py

Use a local master key/cert pair to authenticate to a
[certserver](https://github.com/robot-tools/certserver) instance and retrieve
a system-specific key. Mainly intended to be used with autoimage.py and
systemid.py.

Use the build_image.py flag:

```bash
--module="server/modules/certclient.py --server=https://certserver/ --ca-cert=/path/to/server/cert.pem --client-cert=/path/to/client/cert.pem --client-key=/path/to/client/key.pem --tag=www --subject='/C=US/ST=California/O=XXXX/OU=XXXX Test/CN=SYSTEMID'"
```

The new key and cert are saved to /systemid

`--tag` specifies a value added to the filename, so certclient.py can be
used more than once with different servers (e.g. once for an HTTPS client
key/cert pair, and once for an EAP-TLS key/cert pair).

`--subject` specifics the subject string passed to openssl. `SYSTEMID` is
replaced with the system hostname, possibly as set by systemid.py

### iconograph.py

Install icon inside the image. This allows the image to auto-update over HTTP.
Use the build_image.py flag:

```bash
--module="server/modules/iconograph.py --base-url=http://yourhost/ --ca-cert=/path/to/signing/cert.pem"
```

Optional flags:

`--https-ca-cert` specifies a local path to a PEM-encoded certificate to
validate the HTTPS image server cert against. This differs from `--ca-cert`,
which is used to validate the manifest.json signature.

`--max-images` sets the number of recent images to keep. Older images are
deleted. Defaults to 5. 0 means unlimited.

### persistent.py

Mount a /persistent partition from a filesystem with LABEL=PERSISTENT. Allows
data to persist across reboots, when it would normally be wiped by tmpfs.
Use the build_image.py flag:

```bash
--module="server/modules/persistent.py"
```

See [imager/image.py](imager/image.py)'s or
[server/module/autoimage.py](autoimage.py)'s `--persistent-percent` flag to
create this partition.

### systemid.py

Mount a /systemid partition from a filesystem with LABEL=SYSTEMID. This is
intended to a be separate device (possibly a USB flash drive, SD card, etc.)
which contains data that persists across re-images and identifies the system,
including system-specific keys and certificates.

It also sets the hostname to the value found in the systemid config on the
device.

```bash
--module="server/modules/systemid.py"
```

## Module API

Modules are passed the following long-style arguments:

`--chroot-path` specifies the absolute path to the root of the debootstrap
chroot that will become the root filesystem of the inner image.

## Manifests

Clients download a manifest file to determine available images and to verify
authenticity and integrity of the image. You'll need to generate one on the
server after each new image is built.

Manifest files are signed using OpenSSL. You should run your own CA to do this;
do NOT use a public CA cert. You can find instructions for setting up a CA
[here](https://medium.com/where-the-flamingcow-roams/elliptic-curve-certificate-authority-bbdb9c3855f7#.7v40ox70s).

To build a manifest, run:

```bash
server/publish_manifest.py --cert=/path/to/signing/cert.pem --key=/path/to/signing/key.pem --image-dir=/image/path
```

Optional flags:

`--default-rollout` specifies the percentage rollout for new images; it
defaults to zero. The units are
[basis points](https://en.wikipedia.org/wiki/Basis_point); 10000 means 100%.

`--max-images` sets the number of recent images to keep. Older images are
deleted. Defaults to 0, meaning unlimited.

`--other-cert` specifies a chain certificate, such as your intermediate cert.
It may be specified more than once.

To push a rollout to more targets, edit /image/path/manifest.json.unsigned,
and change rollout_\u2031 (u2031 is ‱, the symbol for basis point). Save,
then re-run publish_manifest.py to generate the signed version.

## Testing with qemu

You can boot images for testing and issue reproduction using qemu.

```base
sudo apt-get install qemu-system-x86_64
sudo kvm_ok
# The above must "KVM acceleration can be used" to be able to get reasonable performance
sudo qemu-system-x86_64 --curses --smp 2 --m 4G --netdev user,id=vmnic --device virtio-net,netdev=vmnic --enable-kvm --cdrom /path/to/image.iso
```

## Imaging

You can write created images to flash drives for installation on other systems,
or manually write them to a drive. To do so:

```bash
# Needs sudo to partition and mkfs devices
sudo imager/image.py --base-url=http://yourhost/ --ca-cert=/path/to/signing/cert.pem --device=/dev/sdx --persistent-percent=50
```

Optional flags:

`--https-ca-cert` specifies a local path to a PEM-encoded certificate to
validate the HTTPS image server cert against. This differs from `--ca-cert`,
which is used to validate the manifest.json signature.

`--https-client-cert` and `--https-client-key` are used together to specify
local paths to a PEM-encoded certificate and key pair that will be provided
to the server over HTTPS. This can be used to limit image availability.
