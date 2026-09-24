import os
import sys
import json
import time
import base64
import socket
import urllib.parse
import subprocess
import atexit
import logging
from typing import Optional, Dict, Any, Tuple
from pathlib import Path

logger = logging.getLogger("ProxyManager")

DEFAULT_SOCKS_PORT = 10888
_XRAY_PROCESS: Optional[subprocess.Popen] = None
_CONFIG_FILE: Optional[Path] = None

def is_port_in_use(port: int, host: str = "127.0.0.1") -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.4)
        return s.connect_ex((host, port)) == 0

def get_free_port(start_port: int = 10880) -> int:
    for port in range(start_port, start_port + 100):
        if not is_port_in_use(port):
            return port
    return start_port

def find_xray_binary() -> Optional[str]:
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

def test_socks5_socket(host: str, port: int, dest_ip: str = "149.154.167.50", dest_port: int = 443, timeout: float = 5.0) -> Tuple[bool, str]:
    """Tests SOCKS5 connectivity by attempting a real MTProto TCP handshake to Telegram DC2."""
    t0 = time.time()
    try:
        s = socket.create_connection((host, port), timeout=timeout)
        s.sendall(b"\x05\x01\x00")
        resp = s.recv(2)
        if resp != b"\x05\x00":
            s.close()
            return False, f"SOCKS5 authentication failed ({resp.hex() if resp else 'empty'})"
        
        ip_bytes = socket.inet_aton(dest_ip)
        req = b"\x05\x01\x00\x01" + ip_bytes + dest_port.to_bytes(2, "big")
        s.sendall(req)
        resp2 = s.recv(10)
        dt = int((time.time() - t0) * 1000)
        s.close()
        if len(resp2) >= 4 and resp2[1] == 0x00:
            return True, f"Telegram connection verified successfully (Latency: {dt}ms)"
        code = resp2[1] if len(resp2) >= 2 else 99
        return False, f"Proxy failed to reach Telegram destination (Error code: {code})"
    except socket.timeout:
        return False, "Connection to Telegram timed out (No response from proxy)"
    except ConnectionRefusedError:
        return False, "Proxy port is closed (Connection refused)"
    except Exception as e:
        return False, f"Network error: {str(e)}"

def parse_vmess(uri: str) -> Dict[str, Any]:
    raw = uri[8:]
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
    raw = uri[5:].split("#")[0]
    if "@" in raw:
        user_info, host_port = raw.split("@", 1)
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

def convert_link_to_xray_config(link: str, listen_port: int) -> Dict[str, Any]:
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
            raise ValueError(f"Unsupported protocol: {scheme}")

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

def check_proxy(proxy_str: str, timeout: float = 6.0) -> Tuple[bool, str]:
    """
    Validates any proxy or V2Ray config against Telegram DC servers.
    Returns (True, message) or (False, error_details).
    """
    if not proxy_str or not proxy_str.strip():
        t0 = time.time()
        try:
            with socket.create_connection(("149.154.167.50", 443), timeout=timeout):
                dt = int((time.time() - t0) * 1000)
                return True, f"Direct connection to Telegram is active (Latency: {dt}ms)"
        except Exception as e:
            return False, f"Direct Telegram connection failed: {e}"

    proxy_str = proxy_str.strip()

    # Direct SOCKS5 / HTTP check
    if proxy_str.startswith("socks5://") or proxy_str.startswith("http://"):
        parsed = urllib.parse.urlparse(proxy_str)
        host = parsed.hostname or "127.0.0.1"
        port = parsed.port or (1080 if "socks" in parsed.scheme else 8080)
        return test_socks5_socket(host, port, timeout=timeout)

    # V2Ray link check
    v2ray_schemes = ("vless://", "vmess://", "trojan://", "ss://")
    if any(proxy_str.startswith(s) for s in v2ray_schemes):
        xray_bin = find_xray_binary()
        if not xray_bin:
            return False, "Xray-core binary not found. Please install Xray first."

        test_port = get_free_port(10890)
        try:
            cfg = convert_link_to_xray_config(proxy_str, test_port)
        except Exception as e:
            return False, f"Invalid link format: {e}"

        temp_cfg_path = Path(__file__).resolve().parent / f".tmp_xray_{test_port}.json"
        try:
            with open(temp_cfg_path, "w", encoding="utf-8") as f:
                json.dump(cfg, f)

            proc = subprocess.Popen([xray_bin, "run", "-c", str(temp_cfg_path)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            
            # Wait for port to open
            for _ in range(15):
                if is_port_in_use(test_port):
                    break
                time.sleep(0.2)

            success, msg = test_socks5_socket("127.0.0.1", test_port, timeout=timeout)
            
            try:
                proc.terminate()
                proc.wait(timeout=1)
            except Exception:
                proc.kill()

            return success, msg
        finally:
            if temp_cfg_path.exists():
                try:
                    temp_cfg_path.unlink()
                except Exception:
                    pass

    return False, "Unsupported proxy format."

def setup_telegram_proxy(proxy_str: Optional[str]) -> Optional[Dict[str, Any]]:
    global _XRAY_PROCESS, _CONFIG_FILE
    if not proxy_str or not proxy_str.strip():
        logger.info("No proxy configured. Telegram client will connect directly.")
        return None

    proxy_str = proxy_str.strip()

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

    v2ray_schemes = ("vless://", "vmess://", "trojan://", "ss://")
    if any(proxy_str.startswith(s) for s in v2ray_schemes):
        xray_bin = find_xray_binary()
        if not xray_bin:
            error_msg = (
                "Xray-core binary not found! Please install Xray or provide a SOCKS5/HTTP proxy."
            )
            logger.error(error_msg)
            raise RuntimeError(error_msg)

        listen_port = get_free_port(DEFAULT_SOCKS_PORT)
        logger.info(f"Parsing V2Ray config ({proxy_str.split('://')[0]})...")
        cfg_dict = convert_link_to_xray_config(proxy_str, listen_port)

        work_dir = Path(__file__).resolve().parent
        _CONFIG_FILE = work_dir / f"xray_auto_{listen_port}.json"
        with open(_CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg_dict, f, indent=2)

        stop_xray()

        logger.info(f"Starting Xray ({xray_bin}) on 127.0.0.1:{listen_port}...")
        _XRAY_PROCESS = subprocess.Popen(
            [xray_bin, "run", "-c", str(_CONFIG_FILE)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )

        for _ in range(20):
            if is_port_in_use(listen_port):
                break
            time.sleep(0.2)

        if not is_port_in_use(listen_port):
            logger.warning(f"Port {listen_port} did not open immediately, continuing...")

        logger.info(f"V2Ray proxy successfully launched on 127.0.0.1:{listen_port}")
        return {
            "scheme": "socks5",
            "hostname": "127.0.0.1",
            "port": listen_port
        }

    if ":" in proxy_str and not proxy_str.startswith("http"):
        parts = proxy_str.split(":")
        return {
            "scheme": "socks5",
            "hostname": parts[0],
            "port": int(parts[1])
        }

    raise ValueError(f"Unknown proxy format: {proxy_str[:25]}...")

if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[1] == "--check":
        target = sys.argv[2]
        ok, reason = check_proxy(target)
        if ok:
            print(f"SUCCESS: {reason}")
            sys.exit(0)
        else:
            print(f"FAILED: {reason}")
            sys.exit(1)
