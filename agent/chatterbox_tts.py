"""
chatterbox_tts.py — Custom LiveKit TTS plugin for a self-hosted Chatterbox
(Resemble AI) voice model, deployed via the devnen/Chatterbox-TTS-Server
FastAPI wrapper (https://github.com/devnen/Chatterbox-TTS-Server) on a
rented GPU (e.g. RunPod RTX 4090).

This is a minimal ChunkedStream-only implementation (no true low-latency
streaming — the self-hosted server generates a full chunk per request, so
there's nothing to gain from a persistent-connection SynthesizeStream here).
It calls the server's OpenAI-compatible endpoint: POST {base_url}/v1/audio/speech

Before relying on this, open http://<your-pod-url>/docs on your deployed
server and confirm the request/response schema matches what's used below —
adjust the JSON body fields or CHATTERBOX_SAMPLE_RATE if your server differs.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

import aiohttp

from livekit.agents import (
    APIConnectionError,
    APIConnectOptions,
    APIStatusError,
    APITimeoutError,
    tts,
    utils,
)
from livekit.agents.types import DEFAULT_API_CONNECT_OPTIONS

DEFAULT_SAMPLE_RATE = 24000  # Chatterbox's typical output rate — verify on your server's /docs


@dataclass
class _TTSOptions:
    base_url: str
    voice: str
    language: str
    sample_rate: int


class TTS(tts.TTS):
    def __init__(
        self,
        *,
        base_url: str,
        voice: str = "default",
        language: str = "hi",
        sample_rate: int = DEFAULT_SAMPLE_RATE,
        http_session: aiohttp.ClientSession | None = None,
    ) -> None:
        super().__init__(
            capabilities=tts.TTSCapabilities(streaming=False),
            sample_rate=sample_rate,
            num_channels=1,
        )
        if not base_url:
            raise ValueError("Chatterbox TTS requires base_url (your RunPod server URL)")

        self._opts = _TTSOptions(
            base_url=base_url.rstrip("/"),
            voice=voice,
            language=language,
            sample_rate=sample_rate,
        )
        self._session = http_session

    @property
    def provider(self) -> str:
        return "Chatterbox"

    def _ensure_session(self) -> aiohttp.ClientSession:
        if not self._session:
            self._session = utils.http_context.http_session()
        return self._session

    def synthesize(
        self, text: str, *, conn_options: APIConnectOptions = DEFAULT_API_CONNECT_OPTIONS
    ) -> "ChunkedStream":
        return ChunkedStream(tts=self, input_text=text, conn_options=conn_options)


class ChunkedStream(tts.ChunkedStream):
    def __init__(self, *, tts: TTS, input_text: str, conn_options: APIConnectOptions) -> None:
        super().__init__(tts=tts, input_text=input_text, conn_options=conn_options)
        self._tts: TTS = tts
        self._opts = tts._opts

    async def _run(self, output_emitter: tts.AudioEmitter) -> None:
        try:
            async with self._tts._ensure_session().post(
                f"{self._opts.base_url}/tts",
                json={
                    "text": self._input_text,
                    "voice_mode": "predefined",
                    "predefined_voice_id": self._opts.voice,
                    "output_format": "wav",
                    "language": self._opts.language,
                    "stream": True,
                    "split_text": True,
                    "chunk_size": 80,  # smaller chunks = faster time-to-first-audio, tune after testing
                },
                timeout=aiohttp.ClientTimeout(
                    total=60,  # first-token latency on a cold GPU pod can be slow — generous timeout for testing
                    sock_connect=self._conn_options.timeout,
                ),
            ) as resp:
                resp.raise_for_status()

                output_emitter.initialize(
                    request_id=utils.shortuuid(),
                    sample_rate=self._opts.sample_rate,
                    num_channels=1,
                    mime_type="audio/wav",
                )

                async for data, _ in resp.content.iter_chunks():
                    output_emitter.push(data)

                output_emitter.flush()

        except asyncio.TimeoutError as e:
            raise APITimeoutError() from e
        except aiohttp.ClientResponseError as e:
            raise APIStatusError(
                message=e.message,
                status_code=e.status,
                request_id=None,
                body=None,
            ) from e
        except Exception as e:
            raise APIConnectionError() from e
