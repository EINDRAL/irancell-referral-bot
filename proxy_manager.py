import os
import sys
import json
import base64
import socket
import urllib.parse
import subprocess
import atexit
import logging
from typing import Optional, Dict, Any, Tuple
from pathlib import Path

logger = logging.getLogger("ProxyManager")

LOCAL_SOCKS_PORT = 10808
_XRAY_PROCESS: Optional[subprocess.Popen] = None
_CONFIG_FILE: Optional[Path] = None

def is_port_in_use(port: int, host: str = "127.0.0.1") -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex((host, port)) == 0

def find_xray_binary() -> Optional[str]:
    # Check standard paths and current dir
    candidates = [
        "xray",
        "/usr/local/bin/xray",
        "/usr/bin/xray",
        str(Path.home() / ".local/bin/xray"),
        str(Path(__file__).resolve().parent / "bin/xray")
    ]
    for c in candidates:
        if os.path.isabs(c):
            if os.path.isfile(c) and os.access(c, os.X_OK):
                return c
        else:
            path = subprocess.run(["which", c], capture_output=True, text=True).stdout.strip()
            if path and os.path.isfile(path) and os.access(path, os.X_OK):
                return path
    return None

def parse_vmess(uri: str) -> Dict[str, Any]:
    raw = uri[8:]
    # Fix base64 padding
    missing_padding = len(raw) % 4
    if missing_padding:
        raw += "=" * (4 - missing_padding)
    decoded = base64.b64decode(raw).decode("utf-8")
    data = json.loads(decoded)

    host = data.get("add", "")
    port = int(data.get("port", 443))
    uuid = data.get("id", "")
    alter_id = int(data.get("aid", 0))
    net = data.get("net", "tcp").lower()
    security = data.get("tls", "none").lower()
    sni = data.get("sni") or data.get("host") or ""
    path = data.get("path", "")

    outbound = {
        "protocol": "vmess",
        "settings": {
            "vnext": [{
                "address": host,
                "port": port,
                "users": [{
                    "id": uuid,
                    "alterId": alter_id,
                    "security": "auto"
                }]
            }]
        },
        "streamSettings": {
            "network": net,
            "security": security if security in ["tls", "none"] else "none"
        }
    }

    if security == "tls":
        outbound["streamSettings"]["tlsSettings"] = {
            "serverName": sni,
            "allowInsecure": False
        }

    if net == "ws":
        outbound["streamSettings"]["wsSettings"] = {
            "path": path,
            "headers": {"Host": sni} if sni else {}
        }
    elif net == "grpc":
        outbound["streamSettings"]["grpcSettings"] = {
            "serviceName": path,
            "multiMode": False
        }

    return outbound

def parse_vless(parsed: urllib.parse.ParseResult) -> Dict[str, Any]:
    uuid = parsed.username
    host = parsed.hostname
    port = parsed.port or 443
    params = urllib.parse.parse_qs(parsed.query)

    def get_p(key: str, default: str = "") -> str:
        return params.get(key, [default])[0]

    net = get_p("type", "tcp").lower()
    security = get_p("security", "none").lower()
    flow = get_p("flow", "")
    sni = get_p("sni") or get_p("host", host)
    pbk = get_p("pbk", "")
    sid = get_p("sid", "")
    spx = get_p("spx", "")
    fp = get_p("fp", "chrome")
    path = get_p("path", "")
    service_name = get_p("serviceName", path)

    user_obj: Dict[str, Any] = {
        "id": uuid,
        "encryption": "none"
    }
    if flow:
        user_obj["flow"] = flow

    outbound = {
        "protocol": "vless",
        "settings": {
            "vnext": [{
                "address": host,
                "port": port,
                "users": [user_obj]
            }]
        },
        "streamSettings": {
            "network": net,
            "security": security
        }
    }

    if security == "reality":
        outbound["streamSettings"]["realitySettings"] = {
            "serverName": sni,
            "fingerprint": fp or "chrome",
            "show": False,
            "publicKey": pbk,
            "shortId": sid,
            "spiderX": spx
        }
    elif security == "tls":
        outbound["streamSettings"]["tlsSettings"] = {
            "serverName": sni,
            "fingerprint": fp or "chrome",
            "allowInsecure": False
        }

    if net == "ws":
        outbound["streamSettings"]["wsSettings"] = {
            "path": path or "/",
            "headers": {"Host": sni} if sni else {}
        }
    elif net == "grpc":
        outbound["streamSettings"]["grpcSettings"] = {
            "serviceName": service_name,
            "multiMode": False
        }

    return outbound

def parse_trojan(parsed: urllib.parse.ParseResult) -> Dict[str, Any]:
    password = parsed.username
    host = parsed.hostname
    port = parsed.port or 443
    params = urllib.parse.parse_qs(parsed.query)

    def get_p(key: str, default: str = "") -> str:
        return params.get(key, [default])[0]

    net = get_p("type", "tcp").lower()
    security = get_p("security", "tls").lower()
    sni = get_p("sni", host)
    path = get_p("path", "")

    outbound = {
        "protocol": "trojan",
        "settings": {
            "servers": [{
                "address": host,
                "port": port,
                "password": password
            }]
        },
        "streamSettings": {
            "network": net,
            "security": security,
            "tlsSettings": {
                "serverName": sni,
                "allowInsecure": False
            }
        }
    }

    if net == "ws":
        outbound["streamSettings"]["wsSettings"] = {
            "path": path or "/",
            "headers": {"Host": sni} if sni else {}
        }
    elif net == "grpc":
        outbound["streamSettings"]["grpcSettings"] = {
            "serviceName": get_p("serviceName", path),
            "multiMode": False
        }

    return outbound

def parse_shadowsocks(uri: str) -> Dict[str, Any]:
    # Formats: ss://base64(method:password@host:port) or ss://base64(method:password)@host:port
    raw = uri[5:].split("#")[0]
    if "@" in raw:
        user_info, host_port = raw.split("@", 1)
        # Pad base64
        pad = len(user_info) % 4
        if pad:
            user_info += "=" * (4 - pad)
        decoded_info = base64.b64decode(user_info).decode("utf-8")
        method, password = decoded_info.split(":", 1)
        host, port_str = host_port.split(":", 1)
        port = int(port_str)
    else:
        pad = len(raw) % 4
        if pad:
            raw += "=" * (4 - pad)
        decoded = base64.b64decode(raw).decode("utf-8")
        # method:password@host:port
        user_part, host_port = decoded.split("@", 1)
        method, password = user_part.split(":", 1)
        host, port_str = host_port.split(":", 1)
        port = int(port_str)

    return {
        "protocol": "shadowsocks",
        "settings": {
            "servers": [{
                "address": host,
                "port": port,
                "method": method,
                "password": password
            }]
        }
    }

def convert_link_to_xray_config(link: str, listen_port: int = LOCAL_SOCKS_PORT) -> Dict[str, Any]:
    link = link.strip()
    if link.startswith("vmess://"):
        outbound = parse_vmess(link)
    elif link.startswith("ss://"):
        outbound = parse_shadowsocks(link)
    else:
        parsed = urllib.parse.urlparse(link)
        scheme = parsed.scheme.lower()
        if scheme == "vless":
            outbound = parse_vless(parsed)
        elif scheme == "trojan":
            outbound = parse_trojan(parsed)
        else:
            raise ValueError(f"پروتکل پشتیبانی‌نشده: {scheme}")

    config = {
        "log": {
            "loglevel": "warning"
        },
        "inbounds": [{
            "listen": "127.0.0.1",
            "port": listen_port,
            "protocol": "socks",
            "settings": {
                "auth": "noauth",
                "udp": True
            }
        }],
        "outbounds": [
            outbound,
            {
                "protocol": "freedom",
                "tag": "direct"
            }
        ]
    }
    return config

def stop_xray():
    global _XRAY_PROCESS, _CONFIG_FILE
    if _XRAY_PROCESS:
        logger.info("Stopping background Xray client...")
        try:
            _XRAY_PROCESS.terminate()
            _XRAY_PROCESS.wait(timeout=2)
        except Exception:
            _XRAY_PROCESS.kill()
        _XRAY_PROCESS = None
    if _CONFIG_FILE and _CONFIG_FILE.exists():
        try:
            _CONFIG_FILE.unlink()
        except Exception:
            pass

atexit.register(stop_xray)

def setup_telegram_proxy(proxy_str: Optional[str]) -> Optional[Dict[str, Any]]:
    """
    Given a proxy string from .env, prepares and returns the Pyrogram proxy dictionary.
    Supports:
      - socks5://[user:pass@]host:port
      - http://[user:pass@]host:port
      - vless://... (via background Xray)
      - vmess://... (via background Xray)
      - trojan://... (via background Xray)
      - ss://... (via background Xray)
    """
    global _XRAY_PROCESS, _CONFIG_FILE
    if not proxy_str or not proxy_str.strip():
        logger.info("No proxy configured. Telegram client will connect directly.")
        return None

    proxy_str = proxy_str.strip()

    # Case 1: Standard SOCKS5 or HTTP
    if proxy_str.startswith("socks5://") or proxy_str.startswith("http://") or proxy_str.startswith("socks4://"):
        parsed = urllib.parse.urlparse(proxy_str)
        scheme = parsed.scheme.lower()
        host = parsed.hostname or "127.0.0.1"
        port = parsed.port or (1080 if "socks" in scheme else 8080)
        proxy_dict = {
            "scheme": scheme,
            "hostname": host,
            "port": port
        }
        if parsed.username:
            proxy_dict["username"] = parsed.username
        if parsed.password:
            proxy_dict["password"] = parsed.password
        logger.info(f"Using direct {scheme.upper()} proxy: {host}:{port}")
        return proxy_dict

    # Case 2: V2Ray link (vless / vmess / trojan / ss)
    v2ray_schemes = ("vless://", "vmess://", "trojan://", "ss://")
    if any(proxy_str.startswith(s) for s in v2ray_schemes):
        xray_bin = find_xray_binary()
        if not xray_bin:
            error_msg = (
                "❌ ابزار Xray برای اجرای کانفیگ V2Ray یافت نشد!\n"
                "لطفاً Xray را نصب کنید یا پروکسی را به صورت socks5:// وارد نمایید."
            )
            logger.error(error_msg)
            raise RuntimeError(error_msg)

        logger.info(f"Parsing V2Ray config ({proxy_str.split('://')[0]})...")
        cfg_dict = convert_link_to_xray_config(proxy_str, LOCAL_SOCKS_PORT)

        # Write temp config
        work_dir = Path(__file__).resolve().parent
        _CONFIG_FILE = work_dir / "xray_auto_config.json"
        with open(_CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg_dict, f, indent=2)

        # Stop old process if running
        stop_xray()

        logger.info(f"Starting Xray ({xray_bin}) on 127.0.0.1:{LOCAL_SOCKS_PORT}...")
        _XRAY_PROCESS = subprocess.Popen(
            [xray_bin, "run", "-c", str(_CONFIG_FILE)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )

        # Wait for socks5 port to be available
        import time
        for _ in range(20):
            if is_port_in_use(LOCAL_SOCKS_PORT):
                break
            time.sleep(0.2)

        if not is_port_in_use(LOCAL_SOCKS_PORT):
            logger.warning("Port 10808 did not open immediately, continuing...")

        logger.info(f"✅ V2Ray proxy successfully launched on 127.0.0.1:{LOCAL_SOCKS_PORT}")
        return {
            "scheme": "socks5",
            "hostname": "127.0.0.1",
            "port": LOCAL_SOCKS_PORT
        }

    # Fallback: maybe just host:port
    if ":" in proxy_str and not proxy_str.startswith("http"):
        parts = proxy_str.split(":")
        return {
            "scheme": "socks5",
            "hostname": parts[0],
            "port": int(parts[1])
        }

    raise ValueError(f"فرمت پروکسی ناشناخته است: {proxy_str[:25]}...")
