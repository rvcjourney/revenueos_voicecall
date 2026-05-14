-- =============================================================================
-- MOTMVoice — Full Database Schema
-- Paste this entire file into Supabase SQL Editor and click Run.
-- Safe to re-run: every statement uses IF NOT EXISTS / OR REPLACE guards.
-- =============================================================================

-- ── Extensions ────────────────────────────────────────────────────────────────
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ── updated_at trigger function ───────────────────────────────────────────────
-- Server-side so raw SQL / Celery tasks always keep the column accurate,
-- not just ORM-issued UPDATEs.
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$;


-- =============================================================================
-- TABLE 1: organizations
-- Root multi-tenant entity. sip_trunk_id FK added after sip_trunks (step 3).
-- =============================================================================
CREATE TABLE IF NOT EXISTS organizations (
    id                      UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    name                    VARCHAR(255) NOT NULL,
    slug                    VARCHAR(100) NOT NULL,
    phone                   VARCHAR(20)  NOT NULL DEFAULT '',
    sip_trunk_id            UUID,                          -- FK added below
    sip_caller_id           VARCHAR(20)  NOT NULL DEFAULT '',
    plan_tier               VARCHAR(50)  NOT NULL DEFAULT 'starter',
    monthly_call_quota      INTEGER      NOT NULL DEFAULT 1000,
    calls_used_this_period  INTEGER      NOT NULL DEFAULT 0,
    billing_period_start    TIMESTAMPTZ  NOT NULL DEFAULT now(),
    billing_period_end      TIMESTAMPTZ  NOT NULL DEFAULT now() + INTERVAL '30 days',
    created_at              TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at              TIMESTAMPTZ  NOT NULL DEFAULT now(),
    deleted_at              TIMESTAMPTZ,
    CONSTRAINT uq_organizations_slug UNIQUE (slug)
);

CREATE UNIQUE INDEX IF NOT EXISTS ix_organizations_slug         ON organizations (slug);
CREATE        INDEX IF NOT EXISTS ix_organizations_sip_trunk_id ON organizations (sip_trunk_id);
CREATE        INDEX IF NOT EXISTS ix_organizations_deleted_at   ON organizations (deleted_at);

DROP TRIGGER IF EXISTS trg_organizations_updated_at ON organizations;
CREATE TRIGGER trg_organizations_updated_at
    BEFORE UPDATE ON organizations
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();


-- =============================================================================
-- TABLE 2: sip_trunks
-- =============================================================================
CREATE TABLE IF NOT EXISTS sip_trunks (
    id               UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id           UUID         NOT NULL REFERENCES organizations (id) ON DELETE CASCADE,
    name             VARCHAR(255) NOT NULL,
    livekit_trunk_id VARCHAR(100) NOT NULL,
    sip_domain       VARCHAR(255) NOT NULL,
    sip_username     VARCHAR(255) NOT NULL,
    sip_password     VARCHAR(255) NOT NULL,
    caller_id        VARCHAR(20)  NOT NULL,
    transport        VARCHAR(16)  NOT NULL DEFAULT 'tcp',
    is_default       BOOLEAN      NOT NULL DEFAULT false,
    is_active        BOOLEAN      NOT NULL DEFAULT true,
    created_at       TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ  NOT NULL DEFAULT now(),
    deleted_at       TIMESTAMPTZ,
    CONSTRAINT ck_sip_trunks_transport CHECK (transport IN ('tcp', 'udp', 'tls'))
);

CREATE INDEX IF NOT EXISTS ix_sip_trunks_org_id     ON sip_trunks (org_id);
CREATE INDEX IF NOT EXISTS ix_sip_trunks_deleted_at ON sip_trunks (deleted_at);

DROP TRIGGER IF EXISTS trg_sip_trunks_updated_at ON sip_trunks;
CREATE TRIGGER trg_sip_trunks_updated_at
    BEFORE UPDATE ON sip_trunks
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();


-- =============================================================================
-- STEP 3: Deferred FK — organizations.sip_trunk_id → sip_trunks
-- Both tables now exist; safe to close the circular reference.
-- =============================================================================
ALTER TABLE organizations
    DROP CONSTRAINT IF EXISTS fk_organizations_default_sip_trunk;
ALTER TABLE organizations
    ADD CONSTRAINT fk_organizations_default_sip_trunk
    FOREIGN KEY (sip_trunk_id) REFERENCES sip_trunks (id) ON DELETE SET NULL;


-- =============================================================================
-- TABLE 4: users
-- =============================================================================
CREATE TABLE IF NOT EXISTS users (
    id              UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id          UUID         NOT NULL REFERENCES organizations (id) ON DELETE CASCADE,
    email           VARCHAR(255) NOT NULL,
    hashed_password VARCHAR(255) NOT NULL,
    full_name       VARCHAR(255) NOT NULL,
    role            VARCHAR(32)  NOT NULL DEFAULT 'agent',
    is_active       BOOLEAN      NOT NULL DEFAULT true,
    last_login_at   TIMESTAMPTZ,
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ  NOT NULL DEFAULT now(),
    deleted_at      TIMESTAMPTZ,
    CONSTRAINT uq_users_email UNIQUE (email),
    CONSTRAINT ck_users_role  CHECK  (role IN ('admin', 'manager', 'agent'))
);

CREATE UNIQUE INDEX IF NOT EXISTS ix_users_email      ON users (email);
CREATE        INDEX IF NOT EXISTS ix_users_org_id     ON users (org_id);
CREATE        INDEX IF NOT EXISTS ix_users_deleted_at ON users (deleted_at);

DROP TRIGGER IF EXISTS trg_users_updated_at ON users;
CREATE TRIGGER trg_users_updated_at
    BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();


-- =============================================================================
-- TABLE 5: agent_templates
-- Reusable voice-agent configurations (system prompt, voice, LLM model).
-- =============================================================================
CREATE TABLE IF NOT EXISTS agent_templates (
    id                        UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id                    UUID         NOT NULL REFERENCES organizations (id) ON DELETE CASCADE,
    created_by_id             UUID         REFERENCES users (id) ON DELETE SET NULL,
    name                      VARCHAR(255) NOT NULL,
    description               TEXT,
    language                  VARCHAR(32)  NOT NULL DEFAULT 'hinglish',
    welcome_message           TEXT         NOT NULL DEFAULT '',
    system_prompt             TEXT         NOT NULL DEFAULT '',
    voice_id                  VARCHAR(100) NOT NULL DEFAULT '9BWtsMINqrJLrRacOk9x',
    voice_provider            VARCHAR(32)  NOT NULL DEFAULT 'elevenlabs',
    llm_model                 VARCHAR(100) NOT NULL DEFAULT 'llama-3.1-8b-instant',
    llm_temperature           FLOAT        NOT NULL DEFAULT 0.7,
    max_call_duration_seconds INTEGER      NOT NULL DEFAULT 600,
    created_at                TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at                TIMESTAMPTZ  NOT NULL DEFAULT now(),
    deleted_at                TIMESTAMPTZ,
    CONSTRAINT ck_agent_templates_language
        CHECK (language IN ('hinglish', 'hindi', 'english', 'marathi')),
    CONSTRAINT ck_agent_templates_voice_provider
        CHECK (voice_provider IN ('elevenlabs', 'deepgram'))
);

CREATE INDEX IF NOT EXISTS ix_agent_templates_org_id        ON agent_templates (org_id);
CREATE INDEX IF NOT EXISTS ix_agent_templates_created_by_id ON agent_templates (created_by_id);
CREATE INDEX IF NOT EXISTS ix_agent_templates_deleted_at    ON agent_templates (deleted_at);

DROP TRIGGER IF EXISTS trg_agent_templates_updated_at ON agent_templates;
CREATE TRIGGER trg_agent_templates_updated_at
    BEFORE UPDATE ON agent_templates
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();


-- =============================================================================
-- TABLE 6: campaigns
-- Batch outbound call campaigns.
-- =============================================================================
CREATE TABLE IF NOT EXISTS campaigns (
    id                   UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id               UUID         NOT NULL REFERENCES organizations (id) ON DELETE CASCADE,
    created_by_id        UUID         REFERENCES users (id) ON DELETE SET NULL,
    name                 VARCHAR(255) NOT NULL,
    description          TEXT,
    goal                 VARCHAR(32)  NOT NULL DEFAULT 'lead_generation',
    agent_template_id    UUID         NOT NULL REFERENCES agent_templates (id) ON DELETE RESTRICT,
    sip_trunk_id         UUID         REFERENCES sip_trunks (id) ON DELETE SET NULL,
    status               VARCHAR(32)  NOT NULL DEFAULT 'draft',
    total_contacts       INTEGER      NOT NULL DEFAULT 0,
    completed_calls      INTEGER      NOT NULL DEFAULT 0,
    interested_count     INTEGER      NOT NULL DEFAULT 0,
    failed_count         INTEGER      NOT NULL DEFAULT 0,
    start_time           TIMESTAMPTZ,
    end_time             TIMESTAMPTZ,
    calling_window_start TIME         NOT NULL DEFAULT '09:00:00',
    calling_window_end   TIME         NOT NULL DEFAULT '19:00:00',
    calling_days         JSONB        NOT NULL DEFAULT '["mon","tue","wed","thu","fri","sat"]'::jsonb,
    timezone             VARCHAR(50)  NOT NULL DEFAULT 'Asia/Kolkata',
    calls_per_minute     INTEGER      NOT NULL DEFAULT 5,
    max_retries          INTEGER      NOT NULL DEFAULT 2,
    retry_after_minutes  INTEGER      NOT NULL DEFAULT 60,
    started_at           TIMESTAMPTZ,
    completed_at         TIMESTAMPTZ,
    created_at           TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at           TIMESTAMPTZ  NOT NULL DEFAULT now(),
    deleted_at           TIMESTAMPTZ,
    CONSTRAINT ck_campaigns_goal
        CHECK (goal IN ('lead_generation', 'follow_up', 'survey', 'announcement')),
    CONSTRAINT ck_campaigns_status
        CHECK (status IN ('draft', 'scheduled', 'running', 'paused', 'completed', 'failed'))
);

CREATE INDEX IF NOT EXISTS ix_campaigns_org_status        ON campaigns (org_id, status);
CREATE INDEX IF NOT EXISTS ix_campaigns_org_id            ON campaigns (org_id);
CREATE INDEX IF NOT EXISTS ix_campaigns_created_by_id     ON campaigns (created_by_id);
CREATE INDEX IF NOT EXISTS ix_campaigns_agent_template_id ON campaigns (agent_template_id);
CREATE INDEX IF NOT EXISTS ix_campaigns_sip_trunk_id      ON campaigns (sip_trunk_id);
CREATE INDEX IF NOT EXISTS ix_campaigns_status            ON campaigns (status);
CREATE INDEX IF NOT EXISTS ix_campaigns_deleted_at        ON campaigns (deleted_at);

DROP TRIGGER IF EXISTS trg_campaigns_updated_at ON campaigns;
CREATE TRIGGER trg_campaigns_updated_at
    BEFORE UPDATE ON campaigns
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();


-- =============================================================================
-- TABLE 7: campaign_contacts
-- Individual contacts within a campaign. Hard-deleted (high volume);
-- history is preserved in the calls table.
-- =============================================================================
CREATE TABLE IF NOT EXISTS campaign_contacts (
    id                UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    campaign_id       UUID         NOT NULL REFERENCES campaigns (id) ON DELETE CASCADE,
    org_id            UUID         NOT NULL REFERENCES organizations (id) ON DELETE CASCADE,
    name              VARCHAR(255) NOT NULL,
    phone             VARCHAR(20)  NOT NULL,
    email             VARCHAR(255),
    company           VARCHAR(255),
    custom_fields     JSONB        NOT NULL DEFAULT '{}'::jsonb,
    status            VARCHAR(32)  NOT NULL DEFAULT 'pending',
    attempt_count     INTEGER      NOT NULL DEFAULT 0,
    last_attempted_at TIMESTAMPTZ,
    created_at        TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ  NOT NULL DEFAULT now(),
    CONSTRAINT ck_campaign_contacts_status
        CHECK (status IN ('pending', 'dialing', 'completed', 'no_answer', 'failed', 'do_not_call'))
);

-- Composite index used by the FOR UPDATE SKIP LOCKED dispatcher
CREATE INDEX IF NOT EXISTS ix_campaign_contacts_campaign_status ON campaign_contacts (campaign_id, status);
-- DNC pre-check
CREATE INDEX IF NOT EXISTS ix_campaign_contacts_org_phone       ON campaign_contacts (org_id, phone);
CREATE INDEX IF NOT EXISTS ix_campaign_contacts_campaign_id     ON campaign_contacts (campaign_id);
CREATE INDEX IF NOT EXISTS ix_campaign_contacts_status          ON campaign_contacts (status);

DROP TRIGGER IF EXISTS trg_campaign_contacts_updated_at ON campaign_contacts;
CREATE TRIGGER trg_campaign_contacts_updated_at
    BEFORE UPDATE ON campaign_contacts
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();


-- =============================================================================
-- TABLE 8: calls
-- Permanent call record. Append-only — never hard or soft deleted.
-- =============================================================================
CREATE TABLE IF NOT EXISTS calls (
    id                UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id            UUID         NOT NULL REFERENCES organizations (id) ON DELETE RESTRICT,
    campaign_id       UUID         REFERENCES campaigns (id) ON DELETE SET NULL,
    contact_id        UUID         REFERENCES campaign_contacts (id) ON DELETE SET NULL,
    livekit_room_name VARCHAR(255) NOT NULL,
    sip_call_id       VARCHAR(255),
    phone_number      VARCHAR(20)  NOT NULL,
    direction         VARCHAR(16)  NOT NULL DEFAULT 'outbound',
    status            VARCHAR(32)  NOT NULL DEFAULT 'initiated',
    outcome           VARCHAR(32)  NOT NULL DEFAULT 'pending',
    started_at        TIMESTAMPTZ,
    answered_at       TIMESTAMPTZ,
    ended_at          TIMESTAMPTZ,
    duration_seconds  INTEGER,
    cost_inr          NUMERIC(10, 2),
    recording_url     VARCHAR(1024),
    summary           TEXT,
    sentiment         VARCHAR(16),
    extracted_data    JSONB        NOT NULL DEFAULT '{}'::jsonb,
    error_message     TEXT,
    created_at        TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ  NOT NULL DEFAULT now(),
    CONSTRAINT uq_calls_livekit_room_name UNIQUE (livekit_room_name),
    CONSTRAINT ck_calls_direction
        CHECK (direction IN ('outbound', 'inbound')),
    CONSTRAINT ck_calls_status
        CHECK (status IN ('initiated', 'ringing', 'connected', 'completed',
                          'no_answer', 'busy', 'failed', 'cancelled')),
    CONSTRAINT ck_calls_outcome
        CHECK (outcome IN ('interested', 'not_interested', 'callback_requested',
                           'wrong_number', 'do_not_call', 'voicemail', 'pending')),
    CONSTRAINT ck_calls_sentiment
        CHECK (sentiment IS NULL OR sentiment IN ('positive', 'neutral', 'negative'))
);

CREATE        INDEX IF NOT EXISTS ix_calls_org_started_at    ON calls (org_id, started_at);
CREATE        INDEX IF NOT EXISTS ix_calls_campaign_outcome  ON calls (campaign_id, outcome);
CREATE        INDEX IF NOT EXISTS ix_calls_org_id            ON calls (org_id);
CREATE        INDEX IF NOT EXISTS ix_calls_campaign_id       ON calls (campaign_id);
CREATE        INDEX IF NOT EXISTS ix_calls_contact_id        ON calls (contact_id);
CREATE UNIQUE INDEX IF NOT EXISTS ix_calls_livekit_room_name ON calls (livekit_room_name);
CREATE        INDEX IF NOT EXISTS ix_calls_phone_number      ON calls (phone_number);
CREATE        INDEX IF NOT EXISTS ix_calls_status            ON calls (status);
CREATE        INDEX IF NOT EXISTS ix_calls_outcome           ON calls (outcome);

DROP TRIGGER IF EXISTS trg_calls_updated_at ON calls;
CREATE TRIGGER trg_calls_updated_at
    BEFORE UPDATE ON calls
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();


-- =============================================================================
-- TABLE 9: call_transcripts
-- One-to-one with calls. Written once; no updated_at (immutable after creation).
-- =============================================================================
CREATE TABLE IF NOT EXISTS call_transcripts (
    id         UUID  PRIMARY KEY DEFAULT gen_random_uuid(),
    call_id    UUID  NOT NULL REFERENCES calls (id) ON DELETE CASCADE,
    segments   JSONB NOT NULL DEFAULT '[]'::jsonb,
    full_text  TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_call_transcripts_call_id UNIQUE (call_id)
);

-- Functional GIN index enables fast full-text search over transcripts
CREATE INDEX IF NOT EXISTS ix_call_transcripts_full_text_gin
    ON call_transcripts
    USING GIN (to_tsvector('english', COALESCE(full_text, '')));


-- =============================================================================
-- TABLE 10: call_events
-- Append-only audit log (state transitions, webhook payloads).
-- Written once; no updated_at.
-- =============================================================================
CREATE TABLE IF NOT EXISTS call_events (
    id         UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    call_id    UUID         NOT NULL REFERENCES calls (id) ON DELETE CASCADE,
    event_type VARCHAR(100) NOT NULL,
    payload    JSONB        NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_call_events_call_id ON call_events (call_id);


-- =============================================================================
-- TABLE 11: api_keys
-- =============================================================================
CREATE TABLE IF NOT EXISTS api_keys (
    id            UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id        UUID         NOT NULL REFERENCES organizations (id) ON DELETE CASCADE,
    created_by_id UUID         REFERENCES users (id) ON DELETE SET NULL,
    name          VARCHAR(255) NOT NULL,
    key_hash      VARCHAR(64)  NOT NULL,
    key_prefix    VARCHAR(20)  NOT NULL,
    last_used_at  TIMESTAMPTZ,
    expires_at    TIMESTAMPTZ,
    revoked_at    TIMESTAMPTZ,
    created_at    TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ  NOT NULL DEFAULT now(),
    CONSTRAINT uq_api_keys_key_hash UNIQUE (key_hash)
);

CREATE INDEX IF NOT EXISTS ix_api_keys_org_id ON api_keys (org_id);

DROP TRIGGER IF EXISTS trg_api_keys_updated_at ON api_keys;
CREATE TRIGGER trg_api_keys_updated_at
    BEFORE UPDATE ON api_keys
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();


-- =============================================================================
-- TABLE 12: do_not_call_entries
-- Per-organisation DNC list.
-- =============================================================================
CREATE TABLE IF NOT EXISTS do_not_call_entries (
    id               UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id           UUID        NOT NULL REFERENCES organizations (id) ON DELETE CASCADE,
    phone_number     VARCHAR(20) NOT NULL,
    reason           VARCHAR(32) NOT NULL,
    source_call_id   UUID        REFERENCES calls (id) ON DELETE SET NULL,
    added_by_user_id UUID        REFERENCES users (id) ON DELETE SET NULL,
    notes            TEXT,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_dnc_org_phone UNIQUE (org_id, phone_number),
    CONSTRAINT ck_do_not_call_entries_reason
        CHECK (reason IN ('user_request', 'wrong_number', 'complaint',
                          'manual_block', 'spam_report'))
);

CREATE INDEX IF NOT EXISTS ix_do_not_call_entries_org_id         ON do_not_call_entries (org_id);
CREATE INDEX IF NOT EXISTS ix_do_not_call_entries_phone_number   ON do_not_call_entries (phone_number);
CREATE INDEX IF NOT EXISTS ix_do_not_call_entries_source_call_id ON do_not_call_entries (source_call_id);

DROP TRIGGER IF EXISTS trg_do_not_call_entries_updated_at ON do_not_call_entries;
CREATE TRIGGER trg_do_not_call_entries_updated_at
    BEFORE UPDATE ON do_not_call_entries
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();


-- =============================================================================
-- TABLE 13: system_dnc_entries
-- Global DNC registry (TRAI NCPR feed etc.) — no org_id.
-- =============================================================================
CREATE TABLE IF NOT EXISTS system_dnc_entries (
    id           UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    phone_number VARCHAR(20) NOT NULL,
    source       VARCHAR(32) NOT NULL,
    imported_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_system_dnc_entries_phone_number UNIQUE (phone_number),
    CONSTRAINT ck_system_dnc_entries_source
        CHECK (source IN ('trai_ncpr', 'manual_admin', 'global_complaint'))
);

CREATE UNIQUE INDEX IF NOT EXISTS ix_system_dnc_entries_phone_number
    ON system_dnc_entries (phone_number);

DROP TRIGGER IF EXISTS trg_system_dnc_entries_updated_at ON system_dnc_entries;
CREATE TRIGGER trg_system_dnc_entries_updated_at
    BEFORE UPDATE ON system_dnc_entries
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();


-- =============================================================================
-- Done. Tables created:
--   organizations, sip_trunks, users, agent_templates,
--   campaigns, campaign_contacts, calls, call_transcripts,
--   call_events, api_keys, do_not_call_entries, system_dnc_entries
-- =============================================================================
