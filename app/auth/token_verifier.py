import os
from jose import jwt, JWTError


class TokenVerifier:
    def __init__(self):
        self.secret = os.getenv("JWT_SECRET")
        self.algorithm = "HS256"  # confirm with backend

    def verify(self, token: str) -> str:
        try:
            payload = jwt.decode(token, self.secret, algorithms=[self.algorithm])
            user_id = payload.get("sub")  # confirm field name with backend
            if not user_id:
                raise ValueError("Token payload missing user identifier")
            return user_id
        except JWTError as e:
            raise ValueError(f"Invalid or expired token: {e}")