import frida
import sys

def on_message(message, data):
    print(f"[{message.get('type')}] {message.get('payload')}")

try:
    print("Finding device...")
    device = frida.get_usb_device(timeout=5)
    print(f"Found device: {device.name}")
except Exception as e:
    print(f"Error finding USB device: {e}")
    sys.exit(1)
