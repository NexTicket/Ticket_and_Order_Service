import os
import firebase_admin
from firebase_admin import credentials, auth
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

# --- Firebase Admin SDK Initialization ---
# Load the path to your service account key from an environment variable
# Example: export FIREBASE_CREDENTIALS_PATH="/path/to/your/serviceAccountKey.json"
cred_path = os.getenv("FIREBASE_SERVICE_ACCOUNT_PATH")
if not cred_path:
    raise ValueError("The FIREBASE_CREDENTIALS_PATH environment variable is not set.")

cred = credentials.Certificate(cred_path)
firebase_admin.initialize_app(cred)

# This is a FastAPI utility that looks for an 'Authorization: Bearer <token>' header
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

def get_current_user_from_token(token: str = Depends(oauth2_scheme)):
    """
    This is a dependency that your endpoints can use.
    It verifies the Firebase ID token and returns the decoded user data.
    """
    try:
        # verify_id_token checks the signature, expiration, and issuer.
        decoded_token = auth.verify_id_token(token)
        return decoded_token
    except firebase_admin.exceptions.FirebaseError as e:
        # This will catch expired tokens, invalid tokens, etc.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid authentication credentials: {e}",
            headers={"WWW-Authenticate": "Bearer"},
        )