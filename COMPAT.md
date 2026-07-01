# Compatibility Notes

## Dev environment (macOS)

The original `requirements.txt` pins 2019-era versions targeting Raspberry Pi OS (Debian Buster). Most of these won't install on macOS with Python 3.9+.

### Known failures
| Package | Pinned | Issue |
|---------|--------|-------|
| `scipy==1.3.1` | needs numpy 1.14.x at build time | fails on Apple Silicon / macOS SDK |
| `tensorflow==1.13.1` | no wheel for Python 3.9+ | source build also fails |
| `numpy==1.20.2` | conflicts with scipy 1.3.1 build deps | version mismatch |
| `dbus-python==1.2.12` | Linux-only | not available on macOS |
| `spidev==3.4` | Pi SPI hardware | not available on macOS |
| `smbus2==0.3.0` | Pi I2C hardware | build fails on macOS |

### Workaround for plugin/UI dev on macOS

Install only the subset needed for Flask web UI and plugin work:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install flask flask-cors flask-wtf PyYAML requests scapy Pillow toml python-dateutil websockets
```

Hardware-specific packages (`spidev`, `smbus2`, `inky`, `dbus-python`) and the AI stack (`tensorflow`, `scipy`, `gym`, `stable-baselines`) are only needed on the actual Pi device.

## Target device

Pwnagotchi runs on Raspberry Pi Zero W (or 2W) with the official OS image. Full dependency install should be done inside the image build, not on a dev Mac.

## Recommended next step

Track requirements modernization as a separate milestone — update pinned versions to current compatible releases, replacing tensorflow 1.x with a maintained equivalent (e.g. TF 2.x or PyTorch).
