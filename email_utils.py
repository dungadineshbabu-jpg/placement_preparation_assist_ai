from itsdangerous import URLSafeTimedSerializer
from flask import current_app

def generate_verification_token(email):
    """
    Generate a secure verification token for email confirmation.
    
    Args:
        email (str): User's email address
    
    Returns:
        str: Signed token for email verification
    """
    serializer = URLSafeTimedSerializer(current_app.config['SECRET_KEY'])
    return serializer.dumps(email, salt='email-verify')


def confirm_verification_token(token, expiration=3600):
    """
    Confirm and decode a verification token.
    
    Args:
        token (str): Verification token from email link
        expiration (int): Token validity in seconds (default: 3600 = 1 hour)
    
    Returns:
        str or None: Email address if token is valid and not expired, else None
    """
    serializer = URLSafeTimedSerializer(current_app.config['SECRET_KEY'])
    try:
        email = serializer.loads(
            token,
            salt='email-verify',
            max_age=expiration
        )
        return email
    except Exception:
        return None


def generate_reset_token(email):
    """
    Generate a password reset token.
    
    Args:
        email (str): User's email address
    
    Returns:
        str: Signed token for password reset
    """
    serializer = URLSafeTimedSerializer(current_app.config['SECRET_KEY'])
    return serializer.dumps(email, salt='password-reset')


def confirm_reset_token(token, expiration=3600):
    """
    Confirm and decode a password reset token.
    
    Args:
        token (str): Reset token from email link
        expiration (int): Token validity in seconds (default: 3600)
    
    Returns:
        str or None: Email address if token is valid, else None
    """
    serializer = URLSafeTimedSerializer(current_app.config['SECRET_KEY'])
    try:
        email = serializer.loads(
            token,
            salt='password-reset',
            max_age=expiration
        )
        return email
    except Exception:
        return None