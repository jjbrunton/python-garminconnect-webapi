from __future__ import annotations

import base64
import os
from datetime import date
from typing import Optional

from fastapi import FastAPI, HTTPException, Depends, Query
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel

from garminconnect import Garmin, GarminConnectAuthenticationError, GarminConnectConnectionError, GarminConnectTooManyRequestsError

app = FastAPI(title="Garmin Connect API Wrapper", version="0.1.0")

security = HTTPBearer(auto_error=False)


class LoginRequest(BaseModel):
    email: Optional[str] = None
    password: Optional[str] = None
    is_cn: bool = False
    return_on_mfa: bool = False


class LoginResponse(BaseModel):
    status: str
    client_state: Optional[dict] = None


class ResumeLoginRequest(BaseModel):
    client_state: dict
    mfa_code: str


class SummaryResponse(BaseModel):
    data: dict


class ActivitiesResponse(BaseModel):
    data: list


def _instantiate_api_from_tokenstore(tokenstore: Optional[str]) -> Optional[Garmin]:
    garmin = Garmin()
    try:
        garmin.login(tokenstore)
        return garmin
    except (FileNotFoundError, GarminConnectAuthenticationError):
        return None


def _raise_from_err(err: Exception):
    if isinstance(err, GarminConnectAuthenticationError):
        raise HTTPException(status_code=401, detail="Authentication error")
    if isinstance(err, GarminConnectTooManyRequestsError):
        raise HTTPException(status_code=429, detail="Too many requests")
    if isinstance(err, GarminConnectConnectionError):
        raise HTTPException(status_code=502, detail="Upstream connection error")
    raise HTTPException(status_code=500, detail=str(err))


@app.get("/healthz")
def healthz():
    return {"status": "ok"}


@app.post("/login", response_model=LoginResponse)
def login(body: LoginRequest):
    tokenstore_env = os.getenv("GARMINTOKENS")
    if tokenstore_env:
        garmin = _instantiate_api_from_tokenstore(tokenstore_env)
        if garmin:
            return {"status": "ok", "client_state": None}

    garmin = Garmin(
        email=body.email,
        password=body.password,
        is_cn=body.is_cn,
        return_on_mfa=body.return_on_mfa,
    )
    try:
        token1, token2 = garmin.login()
        if token1 == "needs_mfa":
            # Return client_state so caller can resume with MFA
            return {"status": "needs_mfa", "client_state": token2}
        # Persist tokens for subsequent runs if desired
        tokenstore = tokenstore_env or os.path.expanduser("~/.garminconnect")
        try:
            garmin.garth.dump(tokenstore)
        except Exception:
            pass
        return {"status": "ok", "client_state": None}
    except Exception as err:
        _raise_from_err(err)


@app.post("/login/resume", response_model=LoginResponse)
def resume_login(body: ResumeLoginRequest):
    garmin = Garmin(return_on_mfa=True)
    try:
        garmin.resume_login(body.client_state, body.mfa_code)
        tokenstore = os.getenv("GARMINTOKENS") or os.path.expanduser("~/.garminconnect")
        try:
            garmin.garth.dump(tokenstore)
        except Exception:
            pass
        return {"status": "ok", "client_state": None}
    except Exception as err:
        _raise_from_err(err)


@app.get("/summary", response_model=SummaryResponse)
def get_user_summary(cdate: str = Query(..., description="Date in YYYY-MM-DD")):
    tokenstore = os.getenv("GARMINTOKENS") or os.path.expanduser("~/.garminconnect")
    garmin = _instantiate_api_from_tokenstore(tokenstore)
    if not garmin:
        raise HTTPException(status_code=401, detail="Not logged in. Use /login first.")
    try:
        data = garmin.get_user_summary(cdate)
        return {"data": data}
    except Exception as err:
        _raise_from_err(err)


@app.get("/activities", response_model=ActivitiesResponse)
def get_activities(start: int = 0, limit: int = 20, activitytype: Optional[str] = None):
    tokenstore = os.getenv("GARMINTOKENS") or os.path.expanduser("~/.garminconnect")
    garmin = _instantiate_api_from_tokenstore(tokenstore)
    if not garmin:
        raise HTTPException(status_code=401, detail="Not logged in. Use /login first.")
    try:
        data = garmin.get_activities(start=start, limit=limit, activitytype=activitytype)
        return {"data": data}
    except Exception as err:
        _raise_from_err(err)


@app.get("/activities/{activity_id}/download")
def download_activity(activity_id: str, fmt: str = Query("TCX", enum=["ORIGINAL", "TCX", "GPX", "KML", "CSV"])):
    tokenstore = os.getenv("GARMINTOKENS") or os.path.expanduser("~/.garminconnect")
    garmin = _instantiate_api_from_tokenstore(tokenstore)
    if not garmin:
        raise HTTPException(status_code=401, detail="Not logged in. Use /login first.")
    try:
        fmt_enum = getattr(Garmin.ActivityDownloadFormat, fmt)
        raw = garmin.download_activity(activity_id, dl_fmt=fmt_enum)
        # Return base64 to keep JSON-friendly response
        return {"activity_id": activity_id, "format": fmt, "data_base64": base64.b64encode(raw).decode("ascii")}
    except Exception as err:
        _raise_from_err(err)


@app.get("/whoami")
def whoami():
    tokenstore = os.getenv("GARMINTOKENS") or os.path.expanduser("~/.garminconnect")
    garmin = _instantiate_api_from_tokenstore(tokenstore)
    if not garmin:
        raise HTTPException(status_code=401, detail="Not logged in. Use /login first.")
    try:
        return {"full_name": garmin.get_full_name(), "unit_system": garmin.get_unit_system()}
    except Exception as err:
        _raise_from_err(err)
