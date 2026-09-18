import socket
import ipaddress

def get_lan_ip() -> str:
    """
    Returns the preferred LAN IP address suitable for devices on the same Wi-Fi.
    Prioritizes 192.168.x.x and 172.16-31.x.x over VPN subnets (like 10.x.x.x).
    """
    candidates = []
    try:
        hostname = socket.gethostname()
        for ip in socket.gethostbyname_ex(hostname)[2]:
            if ip.startswith("127."):
                continue
            try:
                addr = ipaddress.ip_address(ip)
                if addr.is_private:
                    candidates.append(ip)
            except ValueError:
                pass
    except Exception:
        pass

    # Sort priority: 192.168.x.x > 172.16.x.x - 172.31.x.x > 10.x.x.x > others
    def priority(ip: str) -> int:
        if ip.startswith("192.168."):
            return 1
        if ip.startswith("172."):
            try:
                second = int(ip.split(".")[1])
                if 16 <= second <= 31:
                    return 2
            except (ValueError, IndexError):
                pass
        if ip.startswith("10."):
            return 3
        return 4

    candidates.sort(key=priority)

    if candidates:
        return candidates[0]

    # Ultimate fallback: UDP socket probe
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"

def format_size(size_bytes: int) -> str:
    """Formats bytes into human-readable size (KB, MB, GB)."""
    if not size_bytes or size_bytes < 0:
        return "0 B"
    units = ["B", "KB", "MB", "GB", "TB"]
    unit_idx = 0
    size = float(size_bytes)
    while size >= 1024.0 and unit_idx < len(units) - 1:
        size /= 1024.0
        unit_idx += 1
    return f"{size:.2f} {units[unit_idx]}"
