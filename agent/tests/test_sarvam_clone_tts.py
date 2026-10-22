"""tests/test_sarvam_clone_tts.py — cloned-voice TTS (sarvam_pipeline.SarvamCloneTTS)
against a fake Sarvam WebSocket server speaking the config/text/flush/ping protocol."""
from __future__ import annotations

import asyncio
import base64
import json

import aiohttp
from aiohttp import web
from aiohttp.test_utils import TestServer

import sarvam_pipeline as sp

PCM = base64.b64encode(b"\x00\x00" * 1600).decode()  # 100 ms of 16 kHz silence


class FakeSarvam:
    """mode: "ok" | "error" (error frame after config) | "close" (drop mid-stream)"""

    def __init__(self, mode: str = "ok") -> None:
        self.mode = mode
        self.messages: list[dict] = []
        self.paths: list[str] = []

    async def handler(self, request):
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        self.paths.append(request.path)
        async for msg in ws:
            data = json.loads(msg.data)
            self.messages.append({**data, "_path": request.path})
            if data["type"] == "config" and request.path == "/clone" and self.mode == "error":
                await ws.send_str(json.dumps({"type": "error", "data": {"message": "voice not found", "code": 404, "request_id": "req-err"}}))
            if data["type"] == "flush":
                if request.path == "/clone" and self.mode == "close":
                    await ws.close()
                    break
                await ws.send_str(json.dumps({"type": "audio", "data": {"content_type": "audio/pcm", "audio": PCM, "request_id": "req-1"}}))
                await ws.send_str(json.dumps({"type": "event", "data": {"event_type": "final"}}))
        return ws


async def _server(fake: FakeSarvam) -> TestServer:
    app = web.Application()
    app.router.add_get("/clone", fake.handler)
    app.router.add_get("/tts", fake.handler)
    server = TestServer(app)
    await server.start_server()
    return server


async def _speak(tts, text: str) -> int:
    frames = 0
    stream = tts.stream()
    stream.push_text(text)
    stream.end_input()
    async for _ in stream:
        frames += 1
    await stream.aclose()
    return frames


async def test_config_carries_voice_id_and_target_language_code():
    fake = FakeSarvam()
    server = await _server(fake)
    async with aiohttp.ClientSession() as http:
        tts = sp.SarvamCloneTTS(voice_id="svc-123", target_language_code="ta-IN",
                                ws_url=str(server.make_url("/clone")).replace("http", "ws"),
                                api_key="test", http_session=http)
        assert await _speak(tts, "வணக்கம், நான் பேசுகிறேன்.") > 0
        await tts.aclose()
    await server.close()
    config = next(m for m in fake.messages if m["type"] == "config")["data"]
    assert config["voice_id"] == "svc-123" and config["target_language_code"] == "ta-IN"
    assert config["enable_pretts"] is True
    assert not {"speaker", "model", "language_code", "temperature"} & set(config)
    kinds = [m["type"] for m in fake.messages]
    assert kinds[0] == "config" and "text" in kinds and kinds[-1] == "flush"
    assert all(len(m["data"]["text"]) <= 2500 for m in fake.messages if m["type"] == "text")


async def test_language_switch_reconfigures_same_voice():
    fake = FakeSarvam()
    server = await _server(fake)
    async with aiohttp.ClientSession() as http:
        tts = sp.SarvamCloneTTS(voice_id="svc-123", target_language_code="hi-IN",
                                ws_url=str(server.make_url("/clone")).replace("http", "ws"),
                                api_key="test", http_session=http)
        await _speak(tts, "नमस्ते।")
        tts.update_options(target_language_code="mr-IN")
        await _speak(tts, "नमस्कार।")
        await tts.aclose()
    await server.close()
    configs = [m["data"] for m in fake.messages if m["type"] == "config"]
    assert [c["target_language_code"] for c in configs] == ["hi-IN", "mr-IN"]
    assert {c["voice_id"] for c in configs} == {"svc-123"}


async def _fallback_case(mode: str):
    fake = FakeSarvam(mode)
    server = await _server(fake)
    state = sp.SarvamCallState("tamil", "svc-123", True, {"tamil": {
        "stt": "ta-IN", "tts": "ta-IN", "clone": "ta-IN", "tts_model": "bulbul:v3",
        "voices": [{"id": "ritu", "gender": "female"}]}})
    async with aiohttp.ClientSession() as http:
        adapter = sp.build_tts(state)
        clone, stock = adapter._tts_instances
        clone._opts.ws_url = str(server.make_url("/clone")).replace("http", "ws")
        stock._opts.ws_url = str(server.make_url("/tts")).replace("http", "ws")
        clone._session = stock._session = http
        frames = await _speak(adapter, "வணக்கம், நான் பேசுகிறேன்.")
        await asyncio.sleep(0)
        await adapter.aclose()
    await server.close()
    return state, fake, frames


async def test_error_frame_falls_back_to_stock_voice_and_is_logged():
    state, fake, frames = await _fallback_case("error")
    assert frames > 0  # never silent
    assert state.extra.get("clone_fallback") is True
    assert "/tts" in fake.paths
    stock_cfg = next(m for m in fake.messages if m["type"] == "config" and m["_path"] == "/tts")["data"]
    assert stock_cfg["speaker"] == "ritu" and stock_cfg["target_language_code"] == "ta-IN"


async def test_mid_stream_close_falls_back_to_stock_voice():
    state, fake, frames = await _fallback_case("close")
    assert frames > 0
    assert state.extra.get("clone_fallback") is True


async def test_keepalive_ping_passes_through_proxy():
    fake = FakeSarvam()
    server = await _server(fake)
    async with aiohttp.ClientSession() as http:
        tts = sp.SarvamCloneTTS(voice_id="svc-1", target_language_code="hi-IN",
                                ws_url=str(server.make_url("/clone")).replace("http", "ws"),
                                api_key="test", http_session=http)
        ws = await tts._connect_ws(5.0)
        await ws.send_str(json.dumps({"type": "ping"}))
        await asyncio.sleep(0.05)
        await ws.close()
        await tts.aclose()
    await server.close()
    assert {"type": "ping", "_path": "/clone"} in fake.messages


async def test_interrupted_utterance_leaves_no_stale_audio_for_the_next():
    fake = FakeSarvam()
    slow = fake.handler

    async def delayed(request):  # first utterance answers late; we interrupt before it does
        fake.mode = "ok"
        return await slow(request)
    server = await _server(fake)
    async with aiohttp.ClientSession() as http:
        tts = sp.SarvamCloneTTS(voice_id="svc-1", target_language_code="hi-IN",
                                ws_url=str(server.make_url("/clone")).replace("http", "ws"),
                                api_key="test", http_session=http)
        stream = tts.stream()
        stream.push_text("पहला लंबा वाक्य जो बीच में कट जाएगा।")
        await asyncio.sleep(0.01)
        await stream.aclose()  # caller interrupted
        assert await _speak(tts, "दूसरा वाक्य।") > 0
        await tts.aclose()
    await server.close()
