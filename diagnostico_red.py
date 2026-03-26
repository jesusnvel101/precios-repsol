import socket
import urllib.request
from contextlib import closing

PORT = 8000

def test_url(url: str) -> str:
    try:
        with urllib.request.urlopen(url, timeout=3) as response:
            return f"OK ({response.status})"
    except Exception as e:
        return f"FALLA -> {e}"

def port_open(host: str, port: int) -> str:
    try:
        with closing(socket.create_connection((host, port), timeout=3)):
            return "ABIERTO"
    except Exception as e:
        return f"CERRADO/FALLA -> {e}"

def get_local_ips():
    ips = set()

    hostname = socket.gethostname()
    try:
        for item in socket.getaddrinfo(hostname, None, family=socket.AF_INET):
            ips.add(item[4][0])
    except Exception:
        pass

    # Truco común para obtener IP primaria de salida
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ips.add(s.getsockname()[0])
        s.close()
    except Exception:
        pass

    return sorted(ips)

def main():
    hostname = socket.gethostname()
    print("=" * 60)
    print("DIAGNÓSTICO DE RED LOCAL")
    print("=" * 60)
    print(f"Hostname: {hostname}")
    print()

    ips = get_local_ips()
    print("IPs detectadas:")
    for ip in ips:
        print(f" - {ip}")
    print()

    test_hosts = ["127.0.0.1", "localhost"] + ips

    print(f"Pruebas sobre puerto {PORT}:")
    for host in test_hosts:
        print(f"\nHost: {host}")
        print(f"  Puerto: {port_open(host, PORT)}")

        if host == "localhost":
            url = f"http://localhost:{PORT}"
        else:
            url = f"http://{host}:{PORT}"

        print(f"  HTTP : {test_url(url)}")

    print("\nSugerencias:")
    print("1. Si localhost/127.0.0.1 = OK, tu app sí está corriendo.")
    print("2. Si tu IP local también = OK, al menos tu PC responde en esa interfaz.")
    print("3. Si otra PC no entra, el problema ya es firewall/VPN/red corporativa.")
    print("=" * 60)

if __name__ == "__main__":
    main()