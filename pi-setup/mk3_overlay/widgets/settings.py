"""Settings widget for the MK3 overlay system.

Three pages: General, Library, Network.
Executes system commands directly (sudo reboot, etc.).
Info items query live system state on page enter.
"""
import os
import socket
import subprocess

from ..widget import Widget, Page, ActionItem, ToggleItem, InfoItem
from .. import focus

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(os.path.dirname(SCRIPT_DIR))  # pi-setup/
AUTOUPDATE_FILE = "/etc/mk3-autoupdate"


def _run(args):
    """Run a command, ignoring errors."""
    try:
        subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except FileNotFoundError:
        pass


def _run_wait(args):
    """Run a command and wait for completion. Returns stdout or empty string."""
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=10)
        return result.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return ""


def _get_ip():
    try:
        return _run_wait(["hostname", "-I"]).split()[0]
    except (IndexError, Exception):
        return "unknown"


def _get_hostname():
    return socket.gethostname()


def _get_wifi():
    return _run_wait(["iwgetid", "-r"]) or "not connected"


def _get_version():
    version_file = os.path.join(PROJECT_DIR, "VERSION")
    if os.path.exists(version_file):
        try:
            with open(version_file) as f:
                return f.read().strip()
        except IOError:
            pass
    result = _run_wait(["git", "-C", PROJECT_DIR, "describe", "--tags", "--always"])
    return result or "unknown"


def _get_library_location():
    home = os.path.expanduser("~")
    mixxx_lib = os.path.join(home, ".mixxx", "mixxxdb.sqlite")
    if os.path.exists(mixxx_lib):
        return os.path.dirname(mixxx_lib)
    return "~/.mixxx"


def _autoupdate_enabled():
    return os.path.exists(AUTOUPDATE_FILE)


def _on_autoupdate_toggle(state):
    if state:
        try:
            with open(AUTOUPDATE_FILE, "w") as f:
                f.write("1\n")
        except IOError:
            pass
    else:
        try:
            os.remove(AUTOUPDATE_FILE)
        except OSError:
            pass


def _on_tailscale_toggle(state):
    if state:
        _run(["sudo", "tailscale", "up"])
    else:
        _run(["sudo", "tailscale", "down"])


def _do_reboot():
    _run(["sudo", "reboot"])


def _do_shutdown():
    _run(["sudo", "shutdown", "-h", "now"])


def _do_update():
    update_script = os.path.join(PROJECT_DIR, "mk3-update.sh")
    _run(["sudo", "bash", update_script])


def _do_rescan():
    focus.send_rescan()


def _do_mount_usb():
    try:
        result = subprocess.run(
            ["lsblk", "-rno", "NAME,TYPE,MOUNTPOINT"],
            capture_output=True, text=True, timeout=5,
        )
        for line in result.stdout.strip().split("\n"):
            parts = line.split()
            if len(parts) >= 2 and parts[1] == "part":
                name = parts[0]
                mountpoint = parts[2] if len(parts) > 2 else ""
                if mountpoint in ("/", "/boot", "/boot/firmware"):
                    continue
                if not mountpoint:
                    dev = f"/dev/{name}"
                    mount_dir = f"/media/usb-{name}"
                    os.makedirs(mount_dir, exist_ok=True)
                    subprocess.run(["sudo", "mount", dev, mount_dir], timeout=10)
                    return
    except (subprocess.TimeoutExpired, Exception):
        pass


def _do_unmount_usb():
    import glob as g
    for mount_dir in g.glob("/media/usb-*"):
        try:
            subprocess.run(["sudo", "umount", mount_dir], timeout=10)
            os.rmdir(mount_dir)
        except (subprocess.TimeoutExpired, OSError):
            pass


def _stub():
    pass


def create_settings_widget(position=None):
    """Create and return the settings widget with all three pages configured."""
    pos = position or (0, 0, 480, 272)

    general = Page(title="GENERAL", items=[
        ActionItem(label="Reboot", on_execute=_do_reboot, confirm=True),
        ActionItem(label="Shutdown", on_execute=_do_shutdown, confirm=True),
        ActionItem(label="Check for Updates", on_execute=_do_update),
        ToggleItem(label="Auto-update on boot",
                   state=_autoupdate_enabled(),
                   on_toggle=_on_autoupdate_toggle),
        InfoItem(label="Version", value_fn=_get_version),
    ])

    library = Page(title="LIBRARY", items=[
        ActionItem(label="Rescan Library", on_execute=_do_rescan),
        ActionItem(label="Mount USB Drive", on_execute=_do_mount_usb),
        ActionItem(label="Unmount USB Drive", on_execute=_do_unmount_usb),
        InfoItem(label="Library Location", value_fn=_get_library_location),
    ])

    network = Page(title="NETWORK", items=[
        InfoItem(label="IP Address", value_fn=_get_ip),
        InfoItem(label="Hostname", value_fn=_get_hostname),
        InfoItem(label="WiFi Network", value_fn=_get_wifi),
        ActionItem(label="WiFi Select", on_execute=_stub),
        ToggleItem(label="Tailscale", state=False, on_toggle=_on_tailscale_toggle),
        ToggleItem(label="Hotspot", state=False, on_toggle=lambda s: None),
    ])

    return Widget(
        name="settings",
        position=pos,
        activate_button="settings",
        pages=[general, library, network],
    )
