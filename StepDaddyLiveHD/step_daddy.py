import json
import re
import reflex as rx
from urllib.parse import quote, urlparse
from curl_cffi import AsyncSession
from typing import List
from .utils import encrypt, decrypt, urlsafe_base64, decode_bundle
from rxconfig import config
import html

class Channel(rx.Base):
    id: str
    name: str
    tags: List[str]
    logo: str | None

class StepDaddy:
    def __init__(self):
        socks5 = config.socks5
        if socks5 != "":
            self._session = AsyncSession(proxy="socks5://" + socks5)
        else:
            self._session = AsyncSession()
        
        # Use daddylive.sx as the most stable base URL
        self._base_url = "https://daddylive.sx"
        self.channels = []
        with open("StepDaddyLiveHD/meta.json", "r") as f:
            self._meta = json.load(f)

    def _headers(self, referer: str = None, origin: str = None):
        if referer is None:
            referer = self._base_url
        headers = {
            "Referer": referer,
            "user-agent": "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:137.0) Gecko/20100101 Firefox/137.0",
        }
        if origin:
            headers["Origin"] = origin
        return headers

    async def load_channels(self):
        channels = []
        try:
            # Using the API for more reliable channel loading
            response = await self._session.get(f"{self._base_url}/api.php?type=channels", headers=self._headers())
            if response.status_code == 200 and response.text.strip().startswith('['):
                data = response.json()
                for item in data:
                    channel_name = html.unescape(item.get("name", "Unknown")).replace("#", "")
                    channel_id = item.get("id")
                    meta = self._meta.get("18+" if channel_name.startswith("18+") else channel_name, {})
                    logo = meta.get("logo", "")
                    if logo:
                        logo = f"{config.api_url}/logo/{urlsafe_base64(logo)}"
                    channels.append(Channel(id=str(channel_id), name=channel_name, tags=meta.get("tags", []), logo=logo))
        except Exception:
            pass
        finally:
            self.channels = sorted(channels, key=lambda channel: (channel.name.startswith("18"), channel.name))

    async def stream(self, channel_id: str):
        # Using the API to get the stream URL directly
        api_url = f"{self._base_url}/api.php?type=get_stream&id={channel_id}"
        response = await self._session.get(api_url, headers=self._headers())
        
        if response.status_code != 200:
            raise ValueError("API failed to return stream data")

        data = response.json()
        server_url = data.get("url")
        
        if not server_url:
            raise ValueError("No stream URL found in API response")

        m3u8 = await self._session.get(server_url, headers=self._headers(quote(str(server_url))))
        m3u8_data = ""
        for line in m3u8.text.split("\n"):
            if line.startswith("#EXT-X-KEY:"):
                original_url = re.search(r'URI="(.*?)"', line).group(1)
                line = line.replace(original_url, f"{config.api_url}/key/{encrypt(original_url)}/{encrypt(urlparse(server_url).netloc)}")
            elif line.startswith("http") and config.proxy_content:
                line = f"{config.api_url}/content/{encrypt(line)}"
            m3u8_data += line + "\n"
        return m3u8_data

    async def key(self, url: str, host: str):
        url = decrypt(url)
        host = decrypt(host)
        response = await self._session.get(url, headers=self._headers(f"{host}/", host), timeout=60)
        if response.status_code != 200:
            raise Exception(f"Failed to get key")
        return response.content

    @staticmethod
    def content_url(path: str):
        return decrypt(path)

    def playlist(self):
        data = "#EXTM3U\n"
        for channel in self.channels:
            entry = f" tvg-logo=\"{channel.logo}\",{channel.name}" if channel.logo else f",{channel.name}"
            data += f"#EXTINF:-1{entry}\n{config.api_url}/stream/{channel.id}.m3u8\n"
        return data

    async def schedule(self):
        try:
            response = await self._session.get(f"{self._base_url}/api.php?type=schedule", headers=self._headers())
            if response.status_code == 200 and response.text.strip().startswith('{'):
                return response.json()
            return {}
        except Exception:
            return {}
