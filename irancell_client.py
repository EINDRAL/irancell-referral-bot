import os
import random
import logging
import socket
import aiohttp
from typing import Tuple, Dict, Any, Optional

logger = logging.getLogger("IrancellClient")

BASE_URL = "https://my.irancell.ir"
REFER_URL = f"{BASE_URL}/api/gift/v1/refer_a_friend"
NOTIFY_URL = f"{BASE_URL}/api/gift/v1/refer_a_friend/notify"
PROFILE_URL = f"{BASE_URL}/api/sim/v1/profile"

def get_direct_iran_connector() -> aiohttp.TCPConnector:
    """
    Binds the outgoing TCP socket to the physical network card IP (bypassing TUN/VPN).
    This ensures requests to Iranian domestic services like Irancell route directly.
    """
    bind_ip = os.getenv("IRANCELL_LOCAL_IP")
    if not bind_ip:
        try:
            with open("/proc/net/route") as f:
                for line in f:
                    fields = line.strip().split()
                    if fields[1] == "00000000" and int(fields[3], 16) & 2:
                        iface = fields[0]
                        import fcntl, struct
                        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                        bind_ip = socket.inet_ntoa(fcntl.ioctl(
                            s.fileno(),
                            0x8915,  # SIOCGIFADDR
                            struct.pack("256s", iface[:15].encode("utf-8"))
                        )[20:24])
                        s.close()
                        break
        except Exception:
            pass

    if not bind_ip:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("10.255.255.255", 1))
            bind_ip = s.getsockname()[0]
            s.close()
        except Exception:
            bind_ip = None

    if bind_ip:
        logger.debug(f"Direct Iran routing bound to local IP: {bind_ip}")
        return aiohttp.TCPConnector(local_addr=(bind_ip, 0))
    return aiohttp.TCPConnector()

COMMON_HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "fa",
    "User-Agent": "Mozilla/5.0 (Linux; Android 14; SM-S928B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Mobile Safari/537.36",
    "Content-Type": "application/json",
    "x-app-version": "9.53.0",
    "Origin": "https://my.irancell.ir",
    "Referer": "https://my.irancell.ir/sim/profile",
    "Connection": "keep-alive"
}

# Full list of official Irancell prefixes (mobile voice/data + youth + TD-LTE)
IRANCELL_PREFIXES = [
    "900", "901", "902", "903", "904", "905",
    "930", "933", "935", "936", "937", "938", "939",
    "941"
]

def generate_random_phone(prefix: Optional[str] = None, allowed_prefixes: Optional[list] = None) -> str:
    """Generates a valid 10-digit mobile number starting with 9 (e.g., 9301234567)."""
    prefixes = allowed_prefixes if allowed_prefixes else IRANCELL_PREFIXES
    p = prefix if prefix and prefix in prefixes else random.choice(prefixes)
    # 7 random digits with replacement (allows repeated numbers unlike random.sample)
    digits = "".join(random.choices("0123456789", k=7))
    return f"{p}{digits}"

class IrancellClient:
    def __init__(self, token: str):
        self.token = token.strip()
        
    def _get_headers(self) -> dict:
        headers = dict(COMMON_HEADERS)
        headers["Authorization"] = self.token
        return headers

    async def invite_friend(self, phone_number: str) -> Tuple[bool, str, Optional[int]]:
        """
        Attempts to refer a friend.
        Returns: (success: bool, status_message: str, http_code: int)
        """
        if not self.token:
            return False, "توکن ایرانسل تنظیم نشده است.", 0

        # Normalise phone: needs to be without leading 0 (e.g. 9301234567)
        clean_phone = phone_number.lstrip("0")
        if clean_phone.startswith("98"):
            clean_phone = clean_phone[2:]

        payload = {
            "application_name": "NGMI",
            "friend_numbers": "98",
            "friend_number": f"98{clean_phone}"
        }

        connector = get_direct_iran_connector()
        async with aiohttp.ClientSession(connector=connector, timeout=aiohttp.ClientTimeout(total=20)) as session:
            try:
                # Step 1: Check eligibility & initiate referral
                async with session.post(REFER_URL, json=payload, headers=self._get_headers()) as resp:
                    status = resp.status
                    if status == 401:
                        return False, "token_expired", 401
                    if status == 429:
                        return False, "rate_limited", 429
                    
                    data = await resp.json(content_type=None)
                    msg = data.get("message") if isinstance(data, dict) else ""
                    
                    if status != 200 or msg != "done":
                        reason = data.get("description") or data.get("message") or f"خطا با کد {status}"
                        return False, f"رد درخواست: {reason}", status

                # Step 2: Confirm and send notification SMS
                async with session.post(NOTIFY_URL, json=payload, headers=self._get_headers()) as resp2:
                    status2 = resp2.status
                    if status2 == 401:
                        return False, "token_expired", 401
                    
                    data2 = await resp2.json(content_type=None)
                    if isinstance(data2, dict):
                        err_type = data2.get("type", "")
                        title = data2.get("title", "")
                        if "too_many_request" in err_type or "every 1 minutes" in title:
                            return False, "rate_limited", 429

                    msg2 = data2.get("message") if isinstance(data2, dict) else ""
                    
                    if status2 == 200 and msg2 == "done":
                        return True, "done", 200
                    else:
                        reason2 = data2.get("description") or data2.get("message") or data2.get("title") or f"خطا در ارسال پیامک ({status2})"
                        return False, f"خطا در ناتیفای: {reason2}", status2

            except aiohttp.ClientConnectorError as e:
                return False, f"خطای اتصال به شبکه ایرانسل: {e}", -1
            except Exception as e:
                return False, f"خطای پیش‌بینی نشده: {e}", -1

    async def get_profile(self) -> Tuple[bool, Any]:
        """Queries the user SIM profile information."""
        if not self.token:
            return False, "توکن ایرانسل موجود نیست."

        connector = get_direct_iran_connector()
        async with aiohttp.ClientSession(connector=connector, timeout=aiohttp.ClientTimeout(total=15)) as session:
            try:
                async with session.get(PROFILE_URL, headers=self._get_headers()) as resp:
                    if resp.status == 200:
                        data = await resp.json(content_type=None)
                        return True, data
                    elif resp.status == 401:
                        return False, "token_expired"
                    else:
                        return False, f"کد خطا {resp.status}"
            except Exception as e:
                return False, str(e)
