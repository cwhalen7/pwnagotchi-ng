
import logging
import glob
import os
import time
import subprocess

import json
import shutil
import toml
import sys
import re

from toml.encoder import TomlEncoder, _dump_str
from zipfile import ZipFile
from datetime import datetime
from enum import Enum


class DottedTomlEncoder(TomlEncoder):
    """
    Dumps the toml into the dotted-key format
    """

    def __init__(self, _dict=dict):
        super(DottedTomlEncoder, self).__init__(_dict)

    def dump_list(self, v):
        retval = "["
        # 1 line if its just 1 item; therefore no newline
        if len(v) > 1:
            retval += "\n"
        for u in v:
            retval += " " + str(self.dump_value(u)) + ",\n"
        # 1 line if its just 1 item; remove newline
        if len(v) <= 1:
            retval = retval.rstrip("\n")
        retval += "]"
        return retval

    def dump_sections(self, o, sup):
        retstr = ""
        pre = ""

        if sup:
            pre = sup + "."

        for section, value in o.items():
            section = str(section)
            qsection = section
            if not re.match(r'^[A-Za-z0-9_-]+$', section):
                qsection = _dump_str(section)
            if value is not None:
                if isinstance(value, dict):
                    toadd, _ = self.dump_sections(value, pre + qsection)
                    retstr += toadd
                    # separte sections
                    if not retstr.endswith('\n\n'):
                        retstr += '\n'
                else:
                    retstr += (pre + qsection + " = " +
                                str(self.dump_value(value)) + '\n')
        return (retstr, self._dict())


def parse_version(version):
    """
    Converts a version str to tuple, so that versions can be compared
    """
    return tuple(version.split('.'))


def remove_whitelisted(list_of_handshakes, list_of_whitelisted_strings, valid_on_error=True):
    """
    Removes a given list of whitelisted handshakes from a path list
    """
    filtered = list()
    def normalize(name):
        """
        Only allow alpha/nums
        """
        return str.lower(''.join(c for c in name if c.isalnum()))

    for handshake in list_of_handshakes:
        try:
            normalized_handshake = normalize(os.path.basename(handshake).rstrip('.pcap'))
            for whitelist in list_of_whitelisted_strings:
                normalized_whitelist = normalize(whitelist)
                if normalized_whitelist in normalized_handshake:
                    break
            else:
                filtered.append(handshake)
        except Exception:
            if valid_on_error:
                filtered.append(handshake)
    return filtered



def download_file(url, destination, chunk_size=128):
    import requests
    resp = requests.get(url)
    resp.raise_for_status()

    with open(destination, 'wb') as fd:
        for chunk in resp.iter_content(chunk_size):
            fd.write(chunk)

def unzip(file, destination, strip_dirs=0):
    os.makedirs(destination, exist_ok=True)
    with ZipFile(file, 'r') as zip:
        if strip_dirs:
            for info in zip.infolist():
                new_filename = info.filename.split('/', maxsplit=strip_dirs)[strip_dirs]
                if new_filename:
                    info.filename = new_filename
                    zip.extract(info, destination)
        else:
            zip.extractall(destination)


# https://stackoverflow.com/questions/823196/yaml-merge-in-python
def merge_config(user, default):
    if isinstance(user, dict) and isinstance(default, dict):
        for k, v in default.items():
            if k not in user:
                user[k] = v
            else:
                user[k] = merge_config(user[k], v)
    return user

def keys_to_str(data):
    if isinstance(data,list):
        converted_list = list()
        for item in data:
            if isinstance(item,list) or isinstance(item,dict):
                converted_list.append(keys_to_str(item))
            else:
                converted_list.append(item)
        return converted_list

    converted_dict = dict()
    for key, value in data.items():
        if isinstance(value, list) or isinstance(value, dict):
            converted_dict[str(key)] = keys_to_str(value)
        else:
            converted_dict[str(key)] = value

    return converted_dict

def save_config(config, target):
    with open(target, 'wt') as fp:
        fp.write(toml.dumps(config, encoder=DottedTomlEncoder()))
    return True

def load_config(args):
    default_config_path = os.path.dirname(args.config)
    if not os.path.exists(default_config_path):
        os.makedirs(default_config_path)

    import pwnagotchi
    ref_defaults_file = os.path.join(os.path.dirname(pwnagotchi.__file__), 'defaults.toml')
    ref_defaults_data = None

    # Bookworm moved the boot partition to /boot/firmware; check both locations
    for boot_conf in ['/boot/config.yml', '/boot/firmware/config.yml',
                      '/boot/config.toml', '/boot/firmware/config.toml']:
        if os.path.exists(boot_conf):
            if os.path.exists(args.user_config):
                # merge boot config into existing user config rather than overwriting
                with open(boot_conf) as src, open(args.user_config) as dst:
                    import yaml
                    boot_data = yaml.safe_load(src) if boot_conf.endswith('.yml') else toml.load(src)
                    user_data = toml.load(dst)
                    merged = merge_config(boot_data, user_data)
                save_config(merged, args.user_config)
            else:
                print("installing %s to %s ..." % (boot_conf, args.user_config))
                shutil.move(boot_conf, args.user_config)
            break

    # check for an entire pwnagotchi folder dropped on the boot partition
    for boot_dir in ['/boot/pwnagotchi', '/boot/firmware/pwnagotchi']:
        if os.path.isdir(boot_dir):
            print("installing %s to /etc/pwnagotchi ..." % boot_dir)
            shutil.rmtree('/etc/pwnagotchi', ignore_errors=True)
            shutil.move(boot_dir, '/etc/')
            break

    # if no config is found, copy the defaults
    if not os.path.exists(args.config):
        print("copying %s to %s ..." % (ref_defaults_file, args.config))
        shutil.copy(ref_defaults_file, args.config)
    else:
        with open(ref_defaults_file) as fp:
            ref_defaults_data = fp.read()

        with open(args.config) as fp:
            defaults_data = fp.read()

        if ref_defaults_data != defaults_data:
            print("!!! file in %s is different than release defaults, overwriting !!!" % args.config)
            shutil.copy(ref_defaults_file, args.config)

    # load the defaults
    with open(args.config) as fp:
        config = toml.load(fp)

    # load the user config
    try:
        user_config = None
        yaml_name = args.user_config.replace('.toml', '.yml')
        if not os.path.exists(args.user_config) and os.path.exists(yaml_name):
            # no toml found; convert yaml
            logging.info('Old yaml-config found. Converting to toml...')
            with open(args.user_config, 'w') as toml_file, open(yaml_name) as yaml_file:
                import yaml
                user_config = yaml.safe_load(yaml_file)
                user_config = keys_to_str(user_config)
                toml.dump(user_config, toml_file)
        elif os.path.exists(args.user_config):
            with open(args.user_config) as toml_file:
                user_config = toml.load(toml_file)

        if user_config:
            config = merge_config(user_config, config)
    except Exception as ex:
        logging.error("There was an error processing the configuration file:\n%s ", ex)
        sys.exit(1)

    # dropins
    dropin = config['main']['confd']
    if dropin and os.path.isdir(dropin):
        dropin += '*.toml' if dropin.endswith('/') else '/*.toml'
        for conf in glob.glob(dropin):
            with open(conf) as toml_file:
                additional_config = toml.load(toml_file)
                config = merge_config(additional_config, config)

    # Normalize display type so driver loading doesn't need dozens of aliases.
    # Unknown types fall back to dummydisplay instead of hard-exiting.
    dtype = config['ui']['display']['type']

    # Dummy / development
    if dtype in ('dummy', 'dummydisplay'):
        dtype = 'dummydisplay'

    # LCD / OLED (non-e-ink) displays
    elif dtype in ('wavesharelcd0in96', 'wslcd0in96'):
        dtype = 'wavesharelcd0in96'
    elif dtype in ('wavesharelcd1in3', 'wslcd1in3'):
        dtype = 'wavesharelcd1in3'
    elif dtype in ('wavesharelcd1in8', 'wslcd1in8'):
        dtype = 'wavesharelcd1in8'
    elif dtype in ('wavesharelcd1in9', 'wslcd1in9'):
        dtype = 'wavesharelcd1in9'
    elif dtype in ('wavesharelcd1in14', 'wslcd1in14'):
        dtype = 'wavesharelcd1in14'
    elif dtype in ('wavesharelcd1in28', 'wslcd1in28'):
        dtype = 'wavesharelcd1in28'
    elif dtype in ('wavesharelcd1in47', 'wslcd1in47'):
        dtype = 'wavesharelcd1in47'
    elif dtype in ('wavesharelcd1in54', 'wslcd1in54'):
        dtype = 'wavesharelcd1in54'
    elif dtype in ('wavesharelcd1in69', 'wslcd1in69'):
        dtype = 'wavesharelcd1in69'
    elif dtype in ('wavesharelcd2in0', 'wslcd2in0'):
        dtype = 'wavesharelcd2in0'
    elif dtype in ('wavesharelcd2in4', 'wslcd2in4'):
        dtype = 'wavesharelcd2in4'
    elif dtype in ('waveshare144lcd', 'ws_144', 'ws144', 'waveshare_144', 'waveshare144'):
        dtype = 'waveshare144lcd'
    elif dtype in ('waveshare35lcd',):
        dtype = 'waveshare35lcd'
    elif dtype in ('waveshareoledlcd',):
        dtype = 'waveshareoledlcd'
    elif dtype in ('waveshareoledlcdvert',):
        dtype = 'waveshareoledlcdvert'
    elif dtype in ('oledhat',):
        dtype = 'oledhat'
    elif dtype in ('lcdhat',):
        dtype = 'lcdhat'
    elif dtype in ('i2coled',):
        dtype = 'i2coled'
    elif dtype in ('displayhatmini',):
        dtype = 'displayhatmini'
    elif dtype in ('pirateaudio',):
        dtype = 'pirateaudio'
    elif dtype in ('pitft',):
        dtype = 'pitft'
    elif dtype in ('tftbonnet',):
        dtype = 'tftbonnet'
    elif dtype in ('spotpear24inch',):
        dtype = 'spotpear24inch'

    # Inky / PaPiRus
    elif dtype in ('inky', 'inkyphat'):
        dtype = 'inky'
    elif dtype in ('inkyv2', 'inkyphatv2'):
        dtype = 'inkyv2'
    elif dtype in ('papirus', 'papi'):
        dtype = 'papirus'

    # DFRobot
    elif dtype in ('dfrobot_1', 'df1'):
        dtype = 'dfrobot_1'
    elif dtype in ('dfrobot_2', 'df2'):
        dtype = 'dfrobot_2'

    # Adafruit e-ink
    elif dtype in ('adafruitssd1306i2c',):
        dtype = 'adafruitssd1306i2c'
    elif dtype in ('adafruit2in13_v3', 'adafruit2in13v3', 'af213v3'):
        dtype = 'adafruit2in13_v3'

    # Waveshare e-ink — 1.x inch
    elif dtype in ('waveshare1in02', 'ws1in02', 'ws102'):
        dtype = 'waveshare1in02'
    elif dtype in ('ws_154inch', 'waveshare1in54', 'ws154inch', 'waveshare_154', 'waveshare154'):
        dtype = 'waveshare1in54'
    elif dtype in ('waveshare1in54_v2', 'ws_154inchv2', 'ws154inchv2'):
        dtype = 'waveshare1in54_v2'
    elif dtype in ('waveshare1in54b', 'ws_154inchb', 'ws154inchb'):
        dtype = 'waveshare1in54b'
    elif dtype in ('waveshare1in54b_v2', 'ws_154inchbv2', 'ws154inchbv2'):
        dtype = 'waveshare1in54b_v2'
    elif dtype in ('waveshare1in54c', 'ws1in54c'):
        dtype = 'waveshare1in54c'
    elif dtype in ('waveshare1in64g', 'ws1in64g'):
        dtype = 'waveshare1in64g'

    # Waveshare e-ink — 2.1x inch
    elif dtype in ('ws_1', 'ws1', 'waveshare_1', 'waveshare1', 'waveshare2in13'):
        dtype = 'waveshare_1'
    elif dtype in ('ws_2', 'ws2', 'waveshare_2', 'waveshare2', 'waveshare2in13v2'):
        dtype = 'waveshare_2'
    elif dtype in ('ws_3', 'ws3', 'waveshare_3', 'waveshare3', 'waveshare2in13v3'):
        dtype = 'waveshare_3'
    elif dtype in ('ws_4', 'ws4', 'waveshare_4', 'waveshare4', 'waveshare2in13v4'):
        dtype = 'waveshare_4'
    elif dtype in ('waveshare2in13b_v3', 'ws213bv3', 'waveshare213inb_v3'):
        dtype = 'waveshare2in13b_v3'
    elif dtype in ('ws_213bv4', 'waveshare2in13b_v4', 'ws213bv4', 'waveshare213inb_v4'):
        dtype = 'waveshare2in13b_v4'
    elif dtype in ('ws_213bc', 'ws213bc', 'waveshare2in13bc', 'waveshare213bc'):
        dtype = 'waveshare2in13bc'
    elif dtype in ('ws_213d', 'ws213d', 'waveshare2in13d', 'waveshare213d'):
        dtype = 'waveshare2in13d'
    elif dtype in ('ws_213g', 'waveshare2in13g', 'waveshare213g'):
        dtype = 'waveshare2in13g'

    # Waveshare e-ink — 2.3–2.9 inch
    elif dtype in ('ws_2in36g', 'waveshare2in36g'):
        dtype = 'waveshare2in36g'
    elif dtype in ('ws_2in66', 'waveshare2in66'):
        dtype = 'waveshare2in66'
    elif dtype in ('ws_2in66b', 'waveshare2in66b'):
        dtype = 'waveshare2in66b'
    elif dtype in ('ws_2in66g', 'waveshare2in66g'):
        dtype = 'waveshare2in66g'
    elif dtype in ('ws_27inch', 'ws27inch', 'waveshare2in7', 'waveshare27'):
        dtype = 'waveshare2in7'
    elif dtype in ('ws_2in7v2', 'waveshare2in7_v2', 'waveshare2in7v2'):
        dtype = 'waveshare2in7_v2'
    elif dtype in ('ws_2in7bv2', 'waveshare2in7b_v2', 'waveshare2in7bv2'):
        dtype = 'waveshare2in7b_v2'
    elif dtype in ('ws_2in9', 'waveshare2in9', 'ws29inch', 'waveshare29inch'):
        dtype = 'waveshare2in9'
    elif dtype in ('ws_2in9v2', 'waveshare2in9_v2', 'waveshare2in9v2'):
        dtype = 'waveshare2in9_v2'
    elif dtype in ('ws_2in9bc', 'waveshare2in9bc'):
        dtype = 'waveshare2in9bc'
    elif dtype in ('ws_2in9d', 'waveshare2in9d'):
        dtype = 'waveshare2in9d'
    elif dtype in ('ws_2in9bv3', 'waveshare2in9b_v3', 'waveshare2in9bv3'):
        dtype = 'waveshare2in9b_v3'
    elif dtype in ('ws_2in9bv4', 'waveshare2in9b_v4', 'waveshare2in9bv4'):
        dtype = 'waveshare2in9b_v4'

    # Waveshare e-ink — 3.x inch
    elif dtype in ('ws_3in0g', 'waveshare3in0g'):
        dtype = 'waveshare3in0g'
    elif dtype in ('ws_3in52', 'waveshare3in52'):
        dtype = 'waveshare3in52'
    elif dtype in ('ws_3in7', 'waveshare3in7'):
        dtype = 'waveshare3in7'

    # Waveshare e-ink — 4.x inch
    elif dtype in ('ws_4in01f', 'waveshare4in01f'):
        dtype = 'waveshare4in01f'
    elif dtype in ('ws_4in2', 'waveshare4in2'):
        dtype = 'waveshare4in2'
    elif dtype in ('ws_4in2v2', 'waveshare4in2v2', 'waveshare4in2_v2'):
        dtype = 'waveshare4in2_v2'
    elif dtype in ('ws_4in2bv2', 'waveshare4in2bv2', 'waveshare4in2b_v2'):
        dtype = 'waveshare4in2b_v2'
    elif dtype in ('ws_4in2bc', 'waveshare4in2bc'):
        dtype = 'waveshare4in2bc'
    elif dtype in ('ws_4in26', 'waveshare4in26'):
        dtype = 'waveshare4in26'
    elif dtype in ('ws_4in37g', 'waveshare4in37g'):
        dtype = 'waveshare4in37g'

    # Waveshare e-ink — 5.x inch
    elif dtype in ('ws_5in65f', 'waveshare5in65f'):
        dtype = 'waveshare5in65f'
    elif dtype in ('ws_5in79', 'waveshare5in79'):
        dtype = 'waveshare5in79'
    elif dtype in ('ws_5in79b', 'waveshare5in79b'):
        dtype = 'waveshare5in79b'
    elif dtype in ('ws_5in83', 'waveshare5in83'):
        dtype = 'waveshare5in83'
    elif dtype in ('ws_5in83v2', 'waveshare5in83v2', 'waveshare5in83_v2'):
        dtype = 'waveshare5in83_v2'
    elif dtype in ('ws_5in83bv2', 'waveshare5in83bv2', 'waveshare5in83b_v2'):
        dtype = 'waveshare5in83b_v2'
    elif dtype in ('ws_5in83bc', 'waveshare5in83bc'):
        dtype = 'waveshare5in83bc'

    # Waveshare e-ink — 7.x inch
    elif dtype in ('ws_7in3f', 'waveshare7in3f'):
        dtype = 'waveshare7in3f'
    elif dtype in ('ws_7in3g', 'waveshare7in3g'):
        dtype = 'waveshare7in3g'
    elif dtype in ('ws_7in5', 'waveshare7in5'):
        dtype = 'waveshare7in5'
    elif dtype in ('ws_7in5hd', 'waveshare7in5hd', 'waveshare7in5_HD'):
        dtype = 'waveshare7in5_HD'
    elif dtype in ('ws_7in5v2', 'waveshare7in5v2', 'waveshare7in5_v2'):
        dtype = 'waveshare7in5_v2'
    elif dtype in ('ws_7in5bhd', 'waveshare7in5bhd', 'waveshare7in5b_HD'):
        dtype = 'waveshare7in5b_HD'
    elif dtype in ('ws_7in5bv2', 'waveshare7in5bv2', 'waveshare7in5b_v2'):
        dtype = 'waveshare7in5b_v2'
    elif dtype in ('ws_7in5bc', 'waveshare7in5bc'):
        dtype = 'waveshare7in5bc'

    # Waveshare e-ink — 13.x inch
    elif dtype in ('ws_13in3k', 'waveshare13in3k'):
        dtype = 'waveshare13in3k'

    # WeAct e-ink
    elif dtype in ('weact2in9', 'weact29in'):
        dtype = 'weact2in9'

    else:
        logging.warning("unsupported display type '%s', falling back to dummydisplay" % dtype)
        dtype = 'dummydisplay'

    config['ui']['display']['type'] = dtype
    return config


def secs_to_hhmmss(secs):
    mins, secs = divmod(secs, 60)
    hours, mins = divmod(mins, 60)
    return '%02d:%02d:%02d' % (hours, mins, secs)


def total_unique_handshakes(path):
    expr = os.path.join(path, "*.pcap")
    return len(glob.glob(expr))


def iface_channels(ifname):
    channels = []
    phy = subprocess.getoutput("/sbin/iw %s info | grep wiphy | cut -d ' ' -f 2" % ifname)
    output = subprocess.getoutput(
        "/sbin/iw phy%s channels | grep ' MHz' | grep -v disabled "
        "| sed 's/^.*\\[//g' | sed 's/\\].*$//g'" % phy
    )
    for line in output.split("\n"):
        line = line.strip()
        try:
            channels.append(int(line))
        except ValueError:
            pass
    return channels


def led(on=True):
    with open('/sys/class/leds/led0/brightness', 'w+t') as fp:
        fp.write("%d" % (0 if on is True else 1))


def blink(times=1, delay=0.3):
    for _ in range(0, times):
        led(True)
        time.sleep(delay)
        led(False)
        time.sleep(delay)
    led(True)


class WifiInfo(Enum):
    """
    Fields you can extract from a pcap file
    """
    BSSID = 0
    ESSID = 1
    ENCRYPTION = 2
    CHANNEL = 3
    RSSI = 4


class FieldNotFoundError(Exception):
    pass


def md5(fname):
    """
    https://stackoverflow.com/questions/3431825/generating-an-md5-checksum-of-a-file
    """
    import hashlib
    hash_md5 = hashlib.md5()
    with open(fname, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_md5.update(chunk)
    return hash_md5.hexdigest()


def extract_from_pcap(path, fields):
    """
    Search in pcap-file for specified information

    path: Path to pcap file
    fields: Array of fields that should be extracted

    If a field is not found, FieldNotFoundError is raised
    """
    results = dict()
    for field in fields:
        if not isinstance(field, WifiInfo):
            raise TypeError("Invalid field")

        subtypes = set()

        if field == WifiInfo.BSSID:
            from scapy.layers.dot11 import Dot11Beacon, Dot11ProbeResp, Dot11AssoReq, Dot11ReassoReq, Dot11, sniff
            subtypes.add('beacon')
            bpf_filter = " or ".join([f"wlan type mgt subtype {subtype}" for subtype in subtypes])
            packets = sniff(offline=path, filter=bpf_filter)
            try:
                for packet in packets:
                    if packet.haslayer(Dot11Beacon):
                        if hasattr(packet[Dot11], 'addr3'):
                            results[field] = packet[Dot11].addr3
                            break
                else:  # magic
                    raise FieldNotFoundError("Could not find field [BSSID]")
            except Exception:
                raise FieldNotFoundError("Could not find field [BSSID]")
        elif field == WifiInfo.ESSID:
            from scapy.layers.dot11 import Dot11Beacon, Dot11ReassoReq, Dot11AssoReq, Dot11, sniff, Dot11Elt
            subtypes.add('beacon')
            subtypes.add('assoc-req')
            subtypes.add('reassoc-req')
            bpf_filter = " or ".join([f"wlan type mgt subtype {subtype}" for subtype in subtypes])
            packets = sniff(offline=path, filter=bpf_filter)
            try:
                for packet in packets:
                    if packet.haslayer(Dot11Elt) and hasattr(packet[Dot11Elt], 'info'):
                        results[field] = packet[Dot11Elt].info.decode('utf-8')
                        break
                else:  # magic
                    raise FieldNotFoundError("Could not find field [ESSID]")
            except Exception:
                raise FieldNotFoundError("Could not find field [ESSID]")
        elif field == WifiInfo.ENCRYPTION:
            from scapy.layers.dot11 import Dot11Beacon, sniff
            subtypes.add('beacon')
            bpf_filter = " or ".join([f"wlan type mgt subtype {subtype}" for subtype in subtypes])
            packets = sniff(offline=path, filter=bpf_filter)
            try:
                for packet in packets:
                    if packet.haslayer(Dot11Beacon) and hasattr(packet[Dot11Beacon], 'network_stats'):
                        stats = packet[Dot11Beacon].network_stats()
                        if 'crypto' in stats:
                            results[field] = stats['crypto']  # set with encryption types
                            break
                else:  # magic
                    raise FieldNotFoundError("Could not find field [ENCRYPTION]")
            except Exception:
                raise FieldNotFoundError("Could not find field [ENCRYPTION]")
        elif field == WifiInfo.CHANNEL:
            from scapy.layers.dot11 import sniff, RadioTap
            from pwnagotchi.mesh.wifi import freq_to_channel
            packets = sniff(offline=path, count=1)
            try:
                results[field] = freq_to_channel(packets[0][RadioTap].ChannelFrequency)
            except Exception:
                raise FieldNotFoundError("Could not find field [CHANNEL]")
        elif field == WifiInfo.RSSI:
            from scapy.layers.dot11 import sniff, RadioTap
            from pwnagotchi.mesh.wifi import freq_to_channel
            packets = sniff(offline=path, count=1)
            try:
                results[field] = packets[0][RadioTap].dBm_AntSignal
            except Exception:
                raise FieldNotFoundError("Could not find field [RSSI]")

    return results

class StatusFile(object):
    def __init__(self, path, data_format='raw'):
        self._path = path
        self._updated = None
        self._format = data_format
        self.data = None

        if os.path.exists(path):
            self._updated = datetime.fromtimestamp(os.path.getmtime(path))
            with open(path) as fp:
                if data_format == 'json':
                    self.data = json.load(fp)
                else:
                    self.data = fp.read()

    def data_field_or(self, name, default=""):
        if self.data is not None and name in self.data:
            return self.data[name]
        return default

    def newer_then_minutes(self, minutes):
        return self._updated is not None and ((datetime.now() - self._updated).seconds / 60) < minutes

    def newer_then_hours(self, hours):
        return self._updated is not None and ((datetime.now() - self._updated).seconds / (60 * 60)) < hours

    def newer_then_days(self, days):
        return self._updated is not None and (datetime.now() - self._updated).days < days

    def update(self, data=None):
        from pwnagotchi.fs import ensure_write
        self._updated = datetime.now()
        self.data = data
        with ensure_write(self._path, 'w') as fp:
            if data is None:
                fp.write(str(self._updated))

            elif self._format == 'json':
                json.dump(self.data, fp)

            else:
                fp.write(data)
