"""Génère un certificat self-signed pour MedDeck (HTTPS local).
Valide pour l'IP du serveur + localhost. À relancer si l'IP change.
"""
import os
import datetime
import ipaddress
import socket
from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CERT_DIR = os.path.join(BASE_DIR, 'instance', 'certs')
os.makedirs(CERT_DIR, exist_ok=True)

CERT_PATH = os.path.join(CERT_DIR, 'cert.pem')
KEY_PATH = os.path.join(CERT_DIR, 'key.pem')


def local_ips():
    ips = {'127.0.0.1'}
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None):
            ip = info[4][0]
            # IPv4 du réseau local uniquement
            if ip.count('.') == 3 and not ip.startswith('169.254') and not ip.startswith('172.'):
                ips.add(ip)
    except Exception:
        pass
    return ips


def generate():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    ips = local_ips()
    san = [x509.DNSName('localhost')]
    for ip in ips:
        san.append(x509.IPAddress(ipaddress.ip_address(ip)))

    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.COUNTRY_NAME, 'MA'),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, 'CHU Mohamed VI - SEBM'),
        x509.NameAttribute(NameOID.COMMON_NAME, 'MedDeck'),
    ])

    now = datetime.datetime.utcnow()
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(days=1))
        .not_valid_after(now + datetime.timedelta(days=3650))
        .add_extension(x509.SubjectAlternativeName(san), critical=False)
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .sign(key, hashes.SHA256())
    )

    with open(KEY_PATH, 'wb') as f:
        f.write(key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        ))
    with open(CERT_PATH, 'wb') as f:
        f.write(cert.public_bytes(serialization.Encoding.PEM))

    print('Certificat genere :')
    print('  ', CERT_PATH)
    print('  ', KEY_PATH)
    print('  Valide pour :', ', '.join(sorted(ips)) + ', localhost')


if __name__ == '__main__':
    generate()
