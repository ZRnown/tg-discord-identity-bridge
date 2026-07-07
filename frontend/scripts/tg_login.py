#!/usr/bin/env python3
"""
TG→Discord Bridge — Telegram Login Script

Usage: python tg_login.py '{"action":"send_code","apiId":"...","apiHash":"...","phoneNumber":"...",...}'

Outputs a single JSON line on stdout.
"""
import sys
import json
import asyncio
import os

async def main():
    if len(sys.argv) < 2:
        print(json.dumps({"error": "missing params"}))
        return

    try:
        params = json.loads(sys.argv[1])
    except Exception as e:
        print(json.dumps({"error": f"invalid params: {e}"}))
        return

    action = params.get("action", "")
    api_id = int(params.get("apiId", 0) or 0)
    api_hash = params.get("apiHash", "")
    phone = params.get("phoneNumber", "")
    session_string = params.get("sessionString", "")
    code = params.get("code", "")
    two_factor = params.get("twoFactorPassword", "")

    try:
        from telethon import TelegramClient
        from telethon.sessions import StringSession
        from telethon.errors import SessionPasswordNeededError
    except ImportError:
        print(json.dumps({"error": "telethon not installed. Run: pip install telethon"}))
        return

    client = TelegramClient(StringSession(session_string), api_id, api_hash)

    try:
        await client.connect()

        if action == "connect":
            # Just verify the session works
            if await client.is_user_authorized():
                me = await client.get_me()
                print(json.dumps({"ok": True, "sessionString": client.session.save(), "name": getattr(me, "first_name", "")}))
            else:
                print(json.dumps({"error": "session not authorized"}))
            await client.disconnect()
            return

        if action == "send_code":
            if await client.is_user_authorized():
                # Already logged in
                me = await client.get_me()
                print(json.dumps({"ok": True, "sessionString": client.session.save(), "name": getattr(me, "first_name", "")}))
                await client.disconnect()
                return
            result = await client.send_code_request(phone)
            # Save phone_code_hash for confirm step — store in process temp file
            temp_path = os.path.join(os.getcwd(), ".data", "tg_phone_hash.json")
            os.makedirs(os.path.dirname(temp_path), exist_ok=True)
            with open(temp_path, "w") as f:
                json.dump({"phone_code_hash": result.phone_code_hash, "session_string": client.session.save()}, f)
            print(json.dumps({"needCode": True}))
            await client.disconnect()
            return

        if action == "confirm_code":
            # Load phone_code_hash
            temp_path = os.path.join(os.getcwd(), ".data", "tg_phone_hash.json")
            phone_code_hash = ""
            saved_session = session_string
            try:
                with open(temp_path, "r") as f:
                    data = json.load(f)
                    phone_code_hash = data.get("phone_code_hash", "")
                    saved_session = data.get("session_string", session_string)
            except Exception:
                pass

            # Reconnect with the saved session
            await client.disconnect()
            client = TelegramClient(StringSession(saved_session), api_id, api_hash)
            await client.connect()

            try:
                await client.sign_in(
                    phone=phone,
                    code=code,
                    phone_code_hash=phone_code_hash,
                )
            except SessionPasswordNeededError:
                if two_factor:
                    await client.sign_in(password=two_factor)
                else:
                    print(json.dumps({"needPassword": True}))
                    await client.disconnect()
                    return

            me = await client.get_me()
            final_session = client.session.save()
            # Clean up temp file
            try:
                os.remove(temp_path)
            except Exception:
                pass
            print(json.dumps({"ok": True, "sessionString": final_session, "name": getattr(me, "first_name", "")}))
            await client.disconnect()
            return

        print(json.dumps({"error": f"unknown action: {action}"}))
    except Exception as e:
        print(json.dumps({"error": str(e)}))
    finally:
        try:
            await client.disconnect()
        except Exception:
            pass

asyncio.run(main())
