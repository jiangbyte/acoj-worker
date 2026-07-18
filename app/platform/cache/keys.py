def login_token_key(token: str) -> str:
    return f"login:token:{token}"


def login_account_tokens_key(account_type: str, account_id: str) -> str:
    return f"login:account:{account_type}:{account_id}"


def login_tokens_key() -> str:
    return "login:tokens"


def login_failure_account_key(account_type: str, account: str) -> str:
    return f"login:failure:account:{account_type}:{account}"


def login_failure_ip_key(account_type: str, ip: str) -> str:
    return f"login:failure:ip:{account_type}:{ip}"


def login_lock_account_key(account_type: str, account: str) -> str:
    return f"login:lock:account:{account_type}:{account}"


def login_lock_ip_key(account_type: str, ip: str) -> str:
    return f"login:lock:ip:{account_type}:{ip}"


def password_reset_token_key(account_type: str, email: str) -> str:
    return f"password:reset:{account_type}:{email.strip().lower()}"


def captcha_key(captcha_id: str) -> str:
    return f"captcha:{captcha_id}"


def password_crypto_key(key_id: str) -> str:
    return f"password:crypto:{key_id}"


def cache_key(name: str) -> str:
    return f"Cache:{name}"


def permission_resource_cache_key() -> str:
    return cache_key("permission-resource")


def permission_resource_method_cache_key() -> str:
    return cache_key("permission-resource-method")


def banner_interaction_delta_key() -> str:
    return "banner:interaction:deltas"
