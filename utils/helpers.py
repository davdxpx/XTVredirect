import secrets
import string

def generate_redirect_code(length=32):
    """Generates a secure random code for redirect links."""
    alphabet = string.ascii_letters + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(length))
