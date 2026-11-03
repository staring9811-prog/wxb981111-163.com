"""启动：python run.py [--port 8770]。只监听局域网网卡地址（NFR-007），并打印局域网访问地址。"""
import argparse
import socket

import uvicorn


def lan_ip() -> str:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))  # 不发包，只取出口网卡地址
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


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
