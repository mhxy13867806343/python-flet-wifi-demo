import subprocess
import platform
import re
import os

def _run(cmd):
    proc = subprocess.run(cmd, capture_output=True, text=True)
    return proc.returncode, (proc.stdout or "").strip(), (proc.stderr or "").strip()

def _mac_wifi_device():
    rc, out, err = _run(["/usr/sbin/networksetup", "-listallhardwareports"])
    if rc != 0 or not out:
        return ""
    lines = out.splitlines()
    for i, line in enumerate(lines):
        if line.strip() in ("Hardware Port: Wi-Fi", "Hardware Port: AirPort"):
            for j in range(i + 1, min(i + 6, len(lines))):
                m = re.match(r"Device:\s*(\S+)", lines[j].strip())
                if m:
                    return m.group(1)
    return ""

def get_known_wifi_ssids():
    system = platform.system()
    if system != "Darwin":
        return []
    device = _mac_wifi_device()
    if not device:
        return []
    rc, out, err = _run(["/usr/sbin/networksetup", "-listpreferredwirelessnetworks", device])
    if rc != 0 or not out:
        return []
    lines = out.splitlines()
    if len(lines) <= 1:
        return []
    ssids = []
    for line in lines[1:]:
        s = line.strip()
        if s:
            ssids.append(s)
    return ssids

def _scan_macos_system_profiler():
    rc, out, err = _run(["/usr/sbin/system_profiler", "SPAirPortDataType"])
    if rc != 0 or not out:
        return [], err or "system_profiler 扫描失败"

    wifi_list = []
    ssid = ""
    signal = None
    security = ""

    in_other = False
    for raw in out.splitlines():
        line = raw.rstrip()
        if not line:
            continue
        if line.strip() == "Other Local Wi-Fi Networks:":
            in_other = True
            continue
        if in_other and re.match(r"^\s{4}\S.*:\s*$", line):
            if ssid:
                wifi_list.append(
                    {
                        "ssid": ssid,
                        "bssid": "-",
                        "signal": signal,
                        "security": security or "Unknown",
                    }
                )
            ssid = line.strip()[:-1]
            signal = None
            security = ""
            continue
        if not in_other or not ssid:
            continue

        m = re.match(r"^\s{6}Security:\s*(.+)$", line)
        if m:
            security = m.group(1).strip()
            continue
        m = re.match(r"^\s{6}Signal / Noise:\s*(-?\d+)\s*dBm\s*/\s*-?\d+\s*dBm\s*$", line)
        if m:
            signal = int(m.group(1))
            continue

    if ssid:
        wifi_list.append(
            {
                "ssid": ssid,
                "bssid": "-",
                "signal": signal,
                "security": security or "Unknown",
            }
        )

    return wifi_list, ""

def scan_wifi_list():
    """返回 (wifi_list, error_message)。error_message 为空字符串表示无错误。"""
    system = platform.system()
    wifi_list = []
    error_message = ""
    
    try:
        if system == "Darwin":
            airport_candidates = [
                "/System/Library/PrivateFrameworks/Apple80211.framework/Versions/Current/Resources/airport",
                "/System/Library/PrivateFrameworks/Apple80211.framework/Versions/A/Resources/airport",
                "/System/Library/PrivateFrameworks/Apple80211.framework/Resources/airport",
            ]
            airport_cmd = next((p for p in airport_candidates if os.path.exists(p)), "")
            if not airport_cmd:
                wifi_list, err = _scan_macos_system_profiler()
                if wifi_list:
                    return sorted(wifi_list, key=lambda x: (x["signal"] is None, -(x["signal"] or -999))), ""
                return [], "未找到 macOS airport 工具，且 system_profiler 未能获取附近 Wi‑Fi。"

            rc, output, stderr = _run([airport_cmd, "-s"])
            if rc != 0:
                return [], f"Wi-Fi 扫描失败：{stderr or 'airport 返回非 0 状态码'}"
            if not output:
                return [], "Wi-Fi 扫描结果为空。请检查：Wi‑Fi 是否开启；系统设置→隐私与安全性→定位服务 是否允许当前运行宿主（Terminal/IDE/你的 App）。"

            lines = output.splitlines()
            if len(lines) <= 1:
                return [], "Wi-Fi 扫描结果为空。请检查定位服务权限。"

            pat = re.compile(
                r"^(?P<ssid>.+?)\s+"
                r"(?P<bssid>(?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2})\s+"
                r"(?P<rssi>-?\d+)\s+"
                r"(?P<channel>\S+)\s+"
                r"(?P<ht>[YN])\s+"
                r"(?P<cc>[A-Z]{2})\s*"
                r"(?P<security>.*)$"
            )

            for line in lines[1:]:
                line = line.rstrip()
                if not line:
                    continue
                m = pat.match(line)
                if not m:
                    continue
                ssid = (m.group("ssid") or "").strip()
                bssid = m.group("bssid")
                signal = int(m.group("rssi"))
                security = (m.group("security") or "").strip() or "Open"
                if not ssid:
                    ssid = "<隐藏网络>"
                if not any(w["ssid"] == ssid for w in wifi_list):
                    wifi_list.append(
                        {
                            "ssid": ssid,
                            "bssid": bssid,
                            "signal": signal,
                            "security": security,
                        }
                    )
                        
        elif system == "Windows":
            output = subprocess.check_output(["netsh", "wlan", "show", "networks", "mode=bssid"], text=True, encoding='gbk')
            
            current_ssid = ""
            current_security = ""
            
            for line in output.split('\n'):
                line = line.strip()
                if line.startswith("SSID"):
                    current_ssid = line.split(":")[1].strip()
                elif line.startswith("身份验证") or line.startswith("Authentication"):
                    current_security = line.split(":")[1].strip()
                elif line.startswith("BSSID"):
                    bssid = line.split(":")[1].strip()
                elif line.startswith("信号") or line.startswith("Signal"):
                    signal_percent = int(line.split(":")[1].strip().replace("%", ""))
                    signal_dbm = (signal_percent / 2) - 100
                    
                    if current_ssid and not any(w['ssid'] == current_ssid for w in wifi_list):
                        wifi_list.append({
                            "ssid": current_ssid,
                            "bssid": bssid,
                            "signal": int(signal_dbm),
                            "security": current_security
                        })
                        
        elif system == "Linux":
            output = subprocess.check_output(["nmcli", "-t", "-f", "SSID,BSSID,SIGNAL,SECURITY", "dev", "wifi"], text=True)
            
            for line in output.split('\n'):
                if not line.strip() or line.startswith('--'):
                    continue
                    
                parts = line.split(':')
                if len(parts) >= 4:
                    ssid = parts[0]
                    bssid = ":".join(parts[1:7])
                    signal_percent = int(parts[7])
                    security = ":".join(parts[8:])
                    
                    signal_dbm = (signal_percent / 2) - 100
                    
                    if ssid and not any(w['ssid'] == ssid for w in wifi_list):
                        wifi_list.append({
                            "ssid": ssid,
                            "bssid": bssid,
                            "signal": int(signal_dbm),
                            "security": security if security else "Open"
                        })
                        
    except Exception as e:
        return [], f"获取 Wi-Fi 列表失败: {e}"

    return sorted(wifi_list, key=lambda x: x["signal"], reverse=True), error_message

def get_wifi_list():
    wifi_list, _ = scan_wifi_list()
    return wifi_list

def get_wifi_password(ssid):
    """尝试获取已保存的 Wi-Fi 密码"""
    system = platform.system()
    
    try:
        if system == "Darwin":
            # macOS: security find-generic-password
            output = subprocess.check_output(
                ["security", "find-generic-password", "-D", "AirPort network password", "-a", ssid, "-w"],
                text=True, stderr=subprocess.DEVNULL
            )
            return output.strip()
            
        elif system == "Windows":
            output = subprocess.check_output(
                ["netsh", "wlan", "show", "profile", f"name={ssid}", "key=clear"],
                text=True, encoding='gbk'
            )
            for line in output.split('\n'):
                if "关键内容" in line or "Key Content" in line:
                    return line.split(":")[1].strip()
                    
        elif system == "Linux":
            output = subprocess.check_output(
                ["nmcli", "-s", "-g", "802-11-wireless-security.psk", "connection", "show", ssid],
                text=True, stderr=subprocess.DEVNULL
            )
            return output.strip()
            
    except Exception:
        pass
        
    return ""

def connect_wifi(ssid: str, password: str):
    system = platform.system()
    ssid = (ssid or "").strip()
    password = (password or "").strip()
    if not ssid:
        return False, "SSID 为空"

    try:
        if system == "Darwin":
            device = _mac_wifi_device()
            if not device:
                return False, "未找到 Wi‑Fi 网卡设备"
            cmd = ["/usr/sbin/networksetup", "-setairportnetwork", device, ssid]
            if password:
                cmd.append(password)
            rc, out, err = _run(cmd)
            if rc == 0:
                return True, ""
            return False, err or out or "连接失败"

        if system == "Windows":
            return False, "Windows 连接暂未实现"

        if system == "Linux":
            return False, "Linux 连接暂未实现"

    except Exception as e:
        return False, str(e)

    return False, "不支持的系统"

if __name__ == "__main__":
    print("正在扫描 Wi-Fi...")
    wifis = get_wifi_list()
    for w in wifis:
        print(f"{w['ssid']} - {w['signal']}dBm - {w['security']}")
