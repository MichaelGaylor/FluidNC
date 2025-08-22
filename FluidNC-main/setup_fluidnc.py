import subprocess, sys, os, platform, json, shutil, argparse

def run(cmd, what):
    print(f"\n==> {what}\n$ {' '.join(cmd)}")
    try:
        out = subprocess.run(cmd, check=True, capture_output=True, text=True)
        if out.stdout: print(out.stdout.strip())
        if out.stderr: print(out.stderr.strip())
        return True
    except subprocess.CalledProcessError as e:
        if e.stdout: print(e.stdout)
        print("ERROR:", e.stderr or str(e))
        return False

ap = argparse.ArgumentParser(description="Build / erase / upload FluidNC and upload FS")
ap.add_argument("--env", default=os.environ.get("FLUIDNC_ENV", "wifi"),
                help="PlatformIO environment (default: wifi; e.g. wifi_s3 for ESP32-S3)")
ap.add_argument("--port", default=os.environ.get("FLUIDNC_PORT"),
                help="Serial upload port (e.g. COM7). If omitted, auto-detect; if multiple, prompt.")
ap.add_argument("--no-erase", action="store_true", help="Skip erase step")
ap.add_argument("--no-fs", action="store_true", help="Skip filesystem upload even if data/ exists")
args = ap.parse_args()

# --- pio path ---
pio = shutil.which("pio")
if not pio:
    if platform.system() == "Windows":
        pio = os.path.expanduser(r"~\.platformio\penv\Scripts\pio.exe")
    else:
        pio = os.path.expanduser("~/.platformio/penv/bin/pio")
if not os.path.exists(pio):
    print("PlatformIO not found. Install it or add 'pio' to PATH.")
    sys.exit(1)

def list_ports():
    try:
        out = subprocess.run([pio, "device", "list", "--json-output"],
                             check=True, capture_output=True, text=True)
        return json.loads(out.stdout)
    except Exception:
        return []

def pick_port():
    if args.port:
        return args.port
    devs = list_ports()
    ports = [d["port"] for d in devs if d.get("port")]
    preferred = []
    for d in devs:
        desc = (d.get("description") or "").lower()
        if any(k in desc for k in ["cp210", "silicon labs", "ch340", "wch", "ftdi", "usb serial", "esp"]):
            if d.get("port"):
                preferred.append(d["port"])
    if len(preferred) == 1:
        return preferred[0]
    if len(ports) == 1:
        return ports[0]
    if not ports:
        print("No serial ports found. Plug your ESP32 and try again.")
        sys.exit(1)
    print("Multiple serial ports detected:")
    for i, p in enumerate(ports, 1):
        print(f"  {i}) {p}")
    sel = input("Select port number: ").strip()
    try:
        return ports[int(sel) - 1]
    except Exception:
        print("Invalid selection."); sys.exit(1)

port = pick_port()
print(f"Using upload port: {port}")

# 1) Build firmware
if not run([pio, "run", "-e", args.env], f"Build ({args.env})"):
    sys.exit(1)

# 2) Optional erase (wipes NVS + SPIFFS)
if not args.no_erase:
    if not run([pio, "run", "-e", args.env, "-t", "erase", "--upload-port", port], "Erase flash"):
        sys.exit(1)
else:
    print("\n==> Skipping erase (per --no-erase)")

# 3) Upload firmware
if not run([pio, "run", "-e", args.env, "-t", "upload", "--upload-port", port], "Upload firmware"):
    sys.exit(1)

# 4) Upload filesystem (SPIFFS/LittleFS) if data/ folder exists and not disabled
project_root = os.getcwd()
data_dir = os.path.join(project_root, "FluidNC", "data")
if args.no_fs:
    print("\n==> Skipping filesystem upload (per --no-fs)")
else:
    if os.path.isdir(data_dir):
        # uploadfs will build and flash the FS image for the env's configured filesystem
        if not run([pio, "run", "-e", args.env, "-t", "uploadfs", "--upload-port", port], "Upload filesystem (data/)"):
            print("\nNOTE: Filesystem upload failed. Check that board_build.filesystem matches your data image (spiffs vs littlefs).")
            sys.exit(1)
    else:
        print("\n⚠ No data/ directory found — skipping filesystem upload.")
        print("   If FluidNC complains about missing config.yaml after boot, create a project-level 'data/' folder")
        print("   and put your defaults there (e.g. 'config.yaml' plus any other required files), then run:")
        print(f"     {pio} run -e {args.env} -t uploadfs --upload-port {port}")

print("\n✅ Done. To watch logs:")
print(f"  {pio} device monitor -b 115200 --port {port}")
