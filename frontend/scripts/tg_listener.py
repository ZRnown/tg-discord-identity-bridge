#!/usr/bin/env python3
"""
TG→Discord Bridge — Telegram Message Listener

Listens to specified Telegram groups and outputs JSON events (one per line) on stdout.

Usage: python tg_listener.py '{"apiId":"...","apiHash":"...","sessionString":"...","groupIds":[...]}'

Output format (one JSON per line):
  {"type":"message","groupId":"-100xxx","senderName":"张三","senderUsername":"zhangsan","senderPhotoUrl":"http://localhost:3000/api/bridge/avatar/xxx","text":"消息内容","timestamp":1234567890}
"""
import sys
import json
import asyncio
import os
import io

async def main():
    if len(sys.argv) < 2:
        print(json.dumps({"type": "error", "error": "missing params"}), flush=True)
        return

    try:
        params = json.loads(sys.argv[1])
    except Exception as e:
        print(json.dumps({"type": "error", "error": f"invalid params: {e}"}), flush=True)
        return

    api_id = int(params.get("apiId", 0) or 0)
    api_hash = params.get("apiHash", "")
    session_string = params.get("sessionString", "")
    group_ids = set(str(g) for g in params.get("groupIds", []))

    try:
        from telethon import TelegramClient, events
        from telethon.sessions import StringSession
        from telethon.tl.types import PeerChannel
    except ImportError:
        print(json.dumps({"type": "error", "error": "telethon not installed. Run: pip install telethon"}), flush=True)
        return

    if not session_string:
        print(json.dumps({"type": "error", "error": "no session string — please login first"}), flush=True)
        return

    client = TelegramClient(StringSession(session_string), api_id, api_hash)

    try:
        await client.connect()
        if not await client.is_user_authorized():
            print(json.dumps({"type": "error", "error": "session not authorized"}), flush=True)
            return

        me = await client.get_me()
        print(f"[INFO] Logged in as {getattr(me, 'first_name', '')} {getattr(me, 'last_name', '')}", flush=True)
        print(f"[INFO] Listening to {len(group_ids)} groups: {group_ids}", flush=True)

        # Save local media paths for avatars and message media.
        avatar_base = os.path.join(os.getcwd(), ".data", "tg_avatars")
        media_base = os.path.join(os.getcwd(), ".data", "tg_media")
        os.makedirs(avatar_base, exist_ok=True)
        os.makedirs(media_base, exist_ok=True)

        async def download_avatar(sender, event):
            """Download sender's photo and return a local URL path."""
            try:
                photos = await client.get_profile_photos(sender)
                if photos and len(photos) > 0:
                    photo = photos[0]
                    # Download the photo
                    buf = io.BytesIO()
                    await client.download_profile_photo(sender, file=buf)
                    buf.seek(0)
                    # Save to file
                    photo_id = f"{sender.id}_{photo.id}.jpg"
                    photo_path = os.path.join(avatar_base, photo_id)
                    with open(photo_path, "wb") as f:
                        f.write(buf.read())
                    return f"/api/bridge/avatar/{photo_id}"
            except Exception as e:
                print(f"[WARN] Avatar download failed: {e}", flush=True)
            return None

        @client.on(events.NewMessage())
        async def handler(event):
            try:
                # Get the chat/group ID
                chat = await event.get_chat()
                chat_id = str(event.chat_id)

                # Only process messages from configured groups
                if group_ids and chat_id not in group_ids:
                    return

                # Get sender
                sender = await event.get_sender()
                if sender is None:
                    return

                sender_name = ""
                if hasattr(sender, 'first_name') and sender.first_name:
                    sender_name = sender.first_name
                    if hasattr(sender, 'last_name') and sender.last_name:
                        sender_name += " " + sender.last_name
                elif hasattr(sender, 'title') and sender.title:
                    sender_name = sender.title
                elif hasattr(sender, 'username') and sender.username:
                    sender_name = sender.username

                sender_username = getattr(sender, 'username', '') or ''

                # Get text
                text = event.raw_text or ""
                if hasattr(event, 'message') and event.message:
                    # Check for media
                    if event.message.media:
                        if not text:
                            text = "[媒体消息]"

                # Download avatar
                photo_url = await download_avatar(sender, event)
                media_paths = []
                if getattr(event.message, "media", None):
                    try:
                        downloaded = await client.download_media(event.message, file=media_base)
                        if downloaded:
                            if isinstance(downloaded, list):
                                media_paths.extend(str(p) for p in downloaded if p)
                            else:
                                media_paths.append(str(downloaded))
                    except Exception as e:
                        print(f"[WARN] Media download failed: {e}", flush=True)

                output = {
                    "type": "message",
                    "groupId": chat_id,
                    "senderId": str(getattr(sender, "id", "")),
                    "senderName": sender_name,
                    "senderUsername": sender_username,
                    "senderPhotoUrl": photo_url,
                    "mediaPaths": media_paths,
                    "text": text,
                    "timestamp": event.message.date.isoformat() if hasattr(event.message, 'date') else "",
                }
                print(json.dumps(output, ensure_ascii=False), flush=True)

            except Exception as e:
                print(f"[ERROR] Message handling error: {e}", flush=True)

        print("[INFO] Listening for messages... (Ctrl+C to stop)", flush=True)
        await client.run_until_disconnected()

    except Exception as e:
        print(json.dumps({"type": "error", "error": str(e)}), flush=True)
    finally:
        try:
            await client.disconnect()
        except Exception:
            pass

asyncio.run(main())
