from typing import Tuple

from sqlalchemy import select

from ezply.crypto import encrypt_json, decrypt_json
from ezply.models import AutofillProfile
from ezply.db import async_session_factory


async def save_autofill_profile(display_name: str, profile: dict, passphrase: str) -> AutofillProfile:
    salt, ciphertext = encrypt_json(profile, passphrase)
    async with async_session_factory() as session:
        result = await session.execute(select(AutofillProfile.id).order_by(AutofillProfile.id.desc()).limit(1))
        existing = result.scalar_one_or_none()
        if existing is None:
            autofill = AutofillProfile(display_name=display_name, salt=salt, ciphertext=ciphertext)
            session.add(autofill)
            await session.commit()
            await session.refresh(autofill)
            return autofill
        else:
            autofill = await session.get(AutofillProfile, existing)
            autofill.display_name = display_name
            autofill.salt = salt
            autofill.ciphertext = ciphertext
            await session.commit()
            await session.refresh(autofill)
            return autofill


async def load_autofill_profile(passphrase: str) -> dict:
    async with async_session_factory() as session:
        result = await session.execute(select(AutofillProfile.salt, AutofillProfile.ciphertext).order_by(AutofillProfile.id.desc()).limit(1))
        row = result.first()
        if row is None:
            raise ValueError("No autofill profile saved")
        salt, ciphertext = row
        return decrypt_json(salt, ciphertext, passphrase)
