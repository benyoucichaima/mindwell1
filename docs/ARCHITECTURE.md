# MindWell — Teleconsultation System Architecture v2

## 1. Stack (as implemented in this repo)

| Layer                  | Technology                                                      | Where                                                 |
| ---------------------- | --------------------------------------------------------------- | ----------------------------------------------------- |
| Web backend            | Django 4 (ASGI)                                                 | `mindwell/`                                           |
| Real-time transport    | Django Channels + Daphne (WebSocket)                            | `consultations/consumers.py`, `accounts/consumers.py` |
| Channel layer          | Redis (production) / InMemory (dev)                             | `mindwell/settings.py: CHANNEL_LAYERS`                |
| Video/Audio            | WebRTC (browser-native, DTLS-SRTP E2E encrypted)                | `chat_room.html` — `RTCPeerConnection`                |
| Signaling              | WebSocket through `ConsultationRoomConsumer` (`type: "webrtc_signal"`) | `consultations/consumers.py`                     |
| AI                     | OpenAI API (Whisper STT + GPT-4 medical summary)                | `ai_service/services.py`                              |
| DB                     | PostgreSQL (prod) / SQLite (dev)                                | `consultations/models.py`                             |
| Cache                  | Redis (WebSocket state + session timers)                        | `consultations/scheduling.py`                         |
| Notifications (mobile) | FCM/APNs (web push via service worker)                          | see §3                                                |

> **No polling anywhere.** Every patient→doctor state change travels over a WebSocket event.

---

## 2. Data model additions

```python
class Consultation(models.Model):
    # existing fields...
    started_at        = models.DateTimeField(null=True, blank=True)  # server clock, set at session start
    duration_limit    = models.PositiveIntegerField(default=45)      # minutes, copied from doctor's profile
    end_notified      = models.BooleanField(default=False)           # session_ended already pushed
    doctor_only_ai_summary = models.JSONField(null=True, blank=True)
    audio_transcription_consent = models.BooleanField(default=False)
    audio_transcription_consent_at = models.DateTimeField(null=True, blank=True)
```

### Session timer — server-synced (no client `setInterval` trust)

1. **Server records `started_at = timezone.now()`** (UTC) when the first party enters and the room is opened (`POST /consultations/<id>/session/start/`).
2. **Client asks for server time once**: `GET /api/server-time/` returns `{"server_time": iso}`. Client computes `offset = server_time - Date.now()` once and uses it for every tick — the visible countdown is still smooth, but it is **always derived from the server's `started_at + duration_limit`**, not from the local clock.
3. **Server is authoritative**: a background check on every WS connect and a periodic check (`check_sessions` management command) pushes `session_ended` to both parties when `started_at + duration_limit <= now()` and flips status to `completed`. The client never decides the session is over.

---

## 3. WebSocket event flow

### 3.1 Endpoints

| Socket                               | Path                       | Who                    |
| ------------------------------------ | -------------------------- | ---------------------- |
| Personal notification stream         | `ws/notifications/`        | any authenticated user |
| Consultation room (chat + signaling) | `ws/consultations/<uuid>/` | paid participants only |

### 3.2 Notification payloads (personal stream)

**Server → doctor — instant alert (no refresh needed):**

```json
{
  "type": "session_requested",
  "notification_id": 321,
  "message": "Nouvelle demande de consultation.",
  "consultation_id": "9f0e…",
  "patient_name": "Chaima",
  "session_type": "video",
  "created_at": "2026-11-01T10:00:00Z"
}
```

The booking view persists the `Notification`, then publishes the event to the doctor's `user_<id>` Channels group after the database transaction commits. The doctor dashboard subscribes to `ws/notifications/`. Background push delivery is not wired by this implementation.

**Server → patient — doctor accepted:**

```json
{
  "type": "session_accepted",
  "notification_id": 322,
  "message": "Votre demande de consultation a été acceptée.",
  "consultation_id": "9f0e…",
  "status": "confirmed",
  "doctor_name": "Dr. Ali",
  "payment_required": true,
  "payment_url": "/accounts/payment/9f0e…/"
}
```

When the consultation is already paid, the payload contains `room_url` instead. The patient dashboard routes to the room for paid sessions or to payment when payment is still required. In either case, no refresh or polling is needed.

### 3.3 Room events (in-room socket)

**Client → server — timer sync request:**

```json
{ "kind": "timer_sync" }
```

**Server → client — timer sync response (server-authoritative clock):**

```json
{
  "kind": "timer_state",
  "server_time": "2026-11-01T10:30:00Z",
  "started_at": "2026-11-01T10:15:00Z",
  "duration_limit": 45,
  "remaining_seconds": 1800
}
```

**Server → both — session over (server-triggered, graceful disconnect):**

```json
{
  "kind": "session_ended",
  "server_time": "2026-11-01T11:00:00Z",
  "reason": "time_limit"
}
```

**Chat message (client → server; server → both room participants):**

```json
{ "type": "chat_message", "content": "Bonjour, comment allez-vous ?" }
```

```json
{
  "type": "chat_message_received",
  "kind": "chat",
  "id": 42,
  "sender_id": 17,
  "sender_name": "Chaima",
  "content": "Bonjour, comment allez-vous ?",
  "timestamp": "2026-11-01T10:20:00+01:00"
}
```

**WebRTC signaling (client → server → peer):**

```json
{ "type": "webrtc_signal", "signal_type": "offer", "payload": { "type": "offer", "sdp": "…" } }
{ "type": "webrtc_signal", "signal_type": "answer", "payload": { "type": "answer", "sdp": "…" } }
{ "type": "webrtc_signal", "signal_type": "candidate", "payload": { "candidate": "…", "sdpMid": "0", "sdpMLineIndex": 0 } }
{ "type": "webrtc_signal_received", "signal_type": "offer", "payload": { "type": "offer", "sdp": "…" } }
```

Room clients branch on `type`; chat updates only chat state, while WebRTC frames are passed to the existing peer-connection signaling flow. Legacy `kind: "chat"` and `kind: "signal"` inbound frames remain accepted during client rollout.

---

## 4. WebRTC setup logic (preserved)

Already implemented in `chat_room.html` and `consultations/consumers.py`:

1. `getUserMedia({ audio: true, video })` — falls back to audio-only if the camera is unavailable.
2. `RTCPeerConnection({ iceServers: [{ urls: "stun:stun.l.google.com:19302" }, …TURN] })` — TURN server (e.g. coturn / Agora TURN) is required for patients behind symmetric NATs.
3. `createOffer()` → `setLocalDescription` → send over the WebSocket; peer answers with `setRemoteDescription` + `createAnswer`.
4. ICE candidates exchanged via `signal` frames.
5. Media is protected in transit by WebRTC DTLS-SRTP. In the current peer-to-peer configuration, media does not pass through Django; DTLS-SRTP alone should not be represented as guaranteed end-to-end encryption when an SFU/provider terminates media transport.

### Consent for audio capture

Before audio transcription, the patient records consent from the consultation room. Consent defaults to false and is persisted in `Consultation.audio_transcription_consent`; `generate_ai_summary` refuses to process audio when consent is absent. Consent should be checked again by any recording/upload worker before sending audio to a provider.

---

## 5. AI pipeline — STT → Doctor-Only summary

```
Consent-checked worker receives the audio file
   → Whisper transcription → transcript
   → GPT-4o structured summary prompt (§5.1)
   → Consultation.doctor_only_ai_summary (JSONField) ← not included in patient responses
   → available only to physician-authorized code paths
```

### 5.1 Exact prompt template (medical LLM)

```
SYSTEM (temperature 0.2, JSON response format):

You are an AI clinical documentation assistant embedded in a telemedicine platform.
You support the LICENSED PHYSICIAN who conducted the session. This is an assistive
tool for the licensed physician. Do not provide direct patient-facing diagnoses.
Never communicate with the patient. Your output is read ONLY by the physician.

You will receive a transcript of a teleconsultation session (video/audio). It may
contain informal speech, transcription errors, or both speakers speaking. Use only
what is explicitly in the transcript; do not invent clinical facts.

Return ONLY JSON:
{
  "chief_complaints": ["symptom or complaint in the patient's own words"],
  "symptoms_discussed": ["…"],
  "patient_history": ["relevant history, medications, prior events mentioned"],
  "discussion_points": ["what the doctor and patient discussed"],
  "preliminary_observations": ["objective observations from the transcript, no diagnosis"],
  "suggested_icd10_codes": [
    {"code": "F41.1", "description": "…", "rationale": "quote or paraphrase from the transcript"}
  ],
  "potential_diagnoses": [
    {"working_hypothesis": "…", "confidence": "low|medium|high", "evidence": "…"}
  ],
  "suggested_next_steps": ["e.g. labs, referral, follow-up interval"],
  "suggested_prescriptions": [
    {"medication_class": "…", "note": "suggestion only; physician must verify and prescribe"}
  ],
  "risk_flags": ["self-harm, harm to others, crisis indicators — empty if none"],
  "disclaimer": "Assistive tool for the licensed physician. Not a patient-facing diagnosis."
}

Rules:
- Suggested ICD-10 codes and diagnoses are REFERENCE ONLY for the physician.
- If risk_flags is non-empty, the physician must be alerted immediately.
- If the transcript is too short or ambiguous, return empty arrays and note it in
  preliminary_observations — never fabricate.

USER (interpolated):
Session transcript (with speaker labels P = patient, D = doctor):
{transcript}
Session duration: {duration_minutes} minutes.
Session type: {session_type}.
```

### 5.2 Storage & access control

```python
class SessionSummary(models.Model):
    consultation = models.ForeignKey(Consultation, on_delete=models.CASCADE, related_name='ai_session_summaries')
    transcript   = models.TextField(blank=True)
    payload      = models.JSONField()
    doctor_only  = models.BooleanField(default=True)   # enforced in the view
    created_at   = models.DateTimeField(auto_now_add=True)
```

The view is decorated with `user_passes_test(lambda u: u.user_type == 'psychologue')` **and** re-checks `consultation.psychologue == request.user` — a patient hitting `/ai/summaries/<id>/` gets 404 (not 403, to avoid leaking existence). Patients never receive `ai.*` WebSocket frames either (see `ChatConsumer.ai_update` — only members in the `doctor_<id>` group get them).

### 5.3 Compliance note

For HIPAA-grade compliance, prefer a **self-hosted LLM (Llama 3 + local Whisper)** behind a VPN, or a BAA-backed provider (Azure OpenAI / OpenAI with zero-data-retention). The prompt is identical either way.

---

## 6. Redis for WebSocket state

```python
CHANNEL_LAYERS = {
  "default": {"BACKEND": "channels_redis.core.RedisChannelLayer", "CONFIG": {"hosts": [("redis", 6379)]}}
}
```

Redis is used for:

- channel-layer groups (`user_<id>`, `consultation_<id>`, `doctor_<id>`) — O(1) delivery to any device;
- the server-synced timer (`consultation:<id>:started_at` key with TTL = duration limit) — a periodic check reads it and pushes `session_ended`.

---

## 7. Checklist of what changed vs. what was wrong

| Bug                     | Old behavior                                     | New behavior                                                                                                                     |
| ----------------------- | ------------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------- |
| Patient must refresh    | Booking page reloaded on a timer                 | `session_accepted` pushed over `ws/notifications/`; UI navigates to the room                                                     |
| Doctor misses requests  | Patient page refresh required                    | Instant banner + push notification on the doctor's dashboard                                                                     |
| Timer desync / cheating | Hardcoded `setInterval` + `45` min on the client | Server records `started_at`; client uses the `server_time` offset; server pushes `session_ended` and flips status to `completed` |
| Video/voice             | WebRTC via signaling socket                      | Preserved exactly (DTLS-SRTP); Agora TURN recommended for symmetric NATs                                                         |
| No AI summary           | Only keyword analysis / text summaries           | Whisper STT + GPT-4 medical prompt, doctor-only dashboard                                                                        |
