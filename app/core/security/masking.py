"""Data masking utilities — prevent sensitive information leakage in logs,
audit trails, and API responses.

等保 requirement: sensitive personal data must not be exposed in cleartext
in non-essential contexts.
"""
import re


def mask_email(email: str | None) -> str | None:
    """Mask email: j***@example.com"""
    if not email:
        return email
    at_idx = email.find("@")
    if at_idx < 2:
        return email
    return email[0] + "***" + email[at_idx:]


def mask_phone(phone: str | None) -> str | None:
    """Mask phone: 138****1234"""
    if not phone or len(phone) < 7:
        return phone
    return phone[:3] + "****" + phone[-4:]


def mask_identifier(value: str | None) -> str | None:
    """Auto-detect and mask email or phone. Returns original if not detected."""
    if not value:
        return value
    if "@" in value:
        return mask_email(value)
    if re.fullmatch(r"1\d{10}", value):
        return mask_phone(value)
    return value


def mask_ip(ip: str | None) -> str | None:
    """Mask last octet for IPv4: 192.168.1.*"""
    if not ip:
        return ip
    parts = ip.rsplit(".", 1)
    if len(parts) == 2:
        return parts[0] + ".*"
    return ip
