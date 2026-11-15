"""启动：python run.py [--port 8770]。只监听局域网网卡地址（NFR-007），并打印局域网访问地址。"""
import argparse
import socket

import uvicorn


def _private(ip: str) -> bool:
    """真实局域网地址：10/8、172.16/12、192.168/16。198.18/15 是代理 / VPN（如 Clash TUN）的虚拟网卡，不算。"""
    try:
        a, b = (int(x) for x in ip.split(".")[:2])
    except ValueError:
        return False
    return a == 10 or (a == 172 and 16 <= b <= 31) or (a == 192 and b == 168)


def lan_ip() -> str:
    cands = []
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))  # 不发包，只取出口网卡地址
        cands.append(s.getsockname()[0])
    except OSError:
        pass
    finally:
        s.close()
    try:
        cands += [i[4][0] for i in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET)]
    except OSError:
        pass
    for ip in cands:
        if _private(ip):
            return ip
    return "127.0.0.1"


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8770)
    ap.add_argument("--host", default="")
    a = ap.parse_args()
    host = a.host or lan_ip()
    from pdt.main import create_app
    from pdt.config import data_dir
    app = create_app()
    print(f"品类机会判定台已启动：局域网访问 http://{host}:{a.port}/ ；本机也可用此地址。")
    if (data_dir() / "初始密码.txt").exists():
        print(f"首次使用：初始账号和密码见 {data_dir() / '初始密码.txt'}")
    uvicorn.run(app, host=host, port=a.port, log_level="warning")
