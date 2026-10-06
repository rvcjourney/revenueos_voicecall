-- Voice schema for a shared database (RevenueOSDatabase), equal to alembic head 0040.
-- The voice campaigns table is voice_campaigns so it does not clash with the
-- email tool's campaigns table. RLS is on for every table, no policies.
-- Run once, as one transaction, on a database that has none of these tables.
BEGIN;
CREATE TABLE public.agent_access_requests (
    id uuid NOT NULL,
    agent_id uuid NOT NULL,
    user_id uuid NOT NULL,
    org_id uuid NOT NULL,
    status character varying(20) DEFAULT 'pending'::character varying NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    can_edit boolean DEFAULT false NOT NULL,
    CONSTRAINT ck_agent_access_status CHECK (((status)::text = ANY ((ARRAY['pending'::character varying, 'approved'::character varying, 'rejected'::character varying])::text[])))
);
CREATE TABLE public.agent_creation_requests (
    id uuid NOT NULL,
    org_id uuid NOT NULL,
    user_id uuid NOT NULL,
    agent_name character varying(255) NOT NULL,
    company_name character varying(255) NOT NULL,
    product_service text NOT NULL,
    target_customers text NOT NULL,
    key_points text NOT NULL,
    file_key character varying(500),
    file_name character varying(255),
    status character varying(20) DEFAULT 'pending'::character varying NOT NULL,
    admin_notes text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_agent_creation_status CHECK (((status)::text = ANY ((ARRAY['pending'::character varying, 'reviewed'::character varying])::text[])))
);
CREATE TABLE public.agent_templates (
    id uuid NOT NULL,
    org_id uuid NOT NULL,
    created_by_id uuid,
    name character varying(255) NOT NULL,
    description text,
    language character varying(32) DEFAULT 'hinglish'::character varying NOT NULL,
    welcome_message text DEFAULT ''::text NOT NULL,
    system_prompt text DEFAULT ''::text NOT NULL,
    voice_id character varying(100) DEFAULT '9BWtsMINqrJLrRacOk9x'::character varying NOT NULL,
    voice_provider character varying(32) DEFAULT 'elevenlabs'::character varying NOT NULL,
    llm_model character varying(100) DEFAULT 'qwen/qwen3.6-27b'::character varying NOT NULL,
    llm_temperature double precision DEFAULT '0.7'::double precision NOT NULL,
    max_call_duration_seconds integer DEFAULT 600 NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    deleted_at timestamp with time zone,
    CONSTRAINT ck_agent_templates_language CHECK (((language)::text = ANY ((ARRAY['hinglish'::character varying, 'hindi'::character varying, 'english'::character varying, 'marathi'::character varying])::text[]))),
    CONSTRAINT ck_agent_templates_voice_provider CHECK (((voice_provider)::text = ANY ((ARRAY['elevenlabs'::character varying, 'cartesia'::character varying, 'deepgram'::character varying, 'chatterbox'::character varying, 'sarvam'::character varying])::text[])))
);
CREATE TABLE public.alembic_version (
    version_num character varying(32) NOT NULL
);
CREATE TABLE public.audit_log (
    id uuid NOT NULL,
    actor_type character varying(20) NOT NULL,
    actor_id uuid,
    org_id uuid,
    action character varying(100) NOT NULL,
    target_type character varying(100),
    target_id uuid,
    metadata jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);
CREATE TABLE public.call_events (
    id uuid NOT NULL,
    call_id uuid NOT NULL,
    event_type character varying(100) NOT NULL,
    payload jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);
CREATE TABLE public.call_transcripts (
    id uuid NOT NULL,
    call_id uuid NOT NULL,
    segments jsonb DEFAULT '[]'::jsonb NOT NULL,
    full_text text,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);
CREATE TABLE public.calls (
    id uuid NOT NULL,
    org_id uuid NOT NULL,
    campaign_id uuid,
    contact_id uuid,
    livekit_room_name character varying(255) NOT NULL,
    sip_call_id character varying(255),
    phone_number character varying(20) NOT NULL,
    direction character varying(16) DEFAULT 'outbound'::character varying NOT NULL,
    status character varying(32) DEFAULT 'initiated'::character varying NOT NULL,
    outcome character varying(32) DEFAULT 'pending'::character varying NOT NULL,
    started_at timestamp with time zone,
    answered_at timestamp with time zone,
    ended_at timestamp with time zone,
    duration_seconds integer,
    cost_inr numeric(10,2),
    recording_url character varying(1024),
    summary text,
    sentiment character varying(16),
    extracted_data jsonb DEFAULT '{}'::jsonb NOT NULL,
    error_message text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    sip_trunk_id uuid,
    recording_purged_at timestamp with time zone,
    reported_at timestamp with time zone,
    CONSTRAINT ck_calls_direction CHECK (((direction)::text = ANY ((ARRAY['outbound'::character varying, 'inbound'::character varying])::text[]))),
    CONSTRAINT ck_calls_outcome CHECK (((outcome)::text = ANY ((ARRAY['interested'::character varying, 'not_interested'::character varying, 'callback_requested'::character varying, 'wrong_number'::character varying, 'do_not_call'::character varying, 'voicemail'::character varying, 'pending'::character varying, 'no_answer'::character varying, 'call_dropped'::character varying])::text[]))),
    CONSTRAINT ck_calls_sentiment CHECK (((sentiment IS NULL) OR ((sentiment)::text = ANY ((ARRAY['positive'::character varying, 'neutral'::character varying, 'negative'::character varying])::text[])))),
    CONSTRAINT ck_calls_status CHECK (((status)::text = ANY ((ARRAY['initiated'::character varying, 'ringing'::character varying, 'connected'::character varying, 'completed'::character varying, 'no_answer'::character varying, 'busy'::character varying, 'failed'::character varying, 'cancelled'::character varying])::text[])))
);
CREATE TABLE public.campaign_contacts (
    id uuid NOT NULL,
    campaign_id uuid NOT NULL,
    org_id uuid NOT NULL,
    name character varying(255) NOT NULL,
    phone character varying(20) NOT NULL,
    email character varying(255),
    company character varying(255),
    custom_fields jsonb DEFAULT '{}'::jsonb NOT NULL,
    status character varying(32) DEFAULT 'pending'::character varying NOT NULL,
    attempt_count integer DEFAULT 0 NOT NULL,
    last_attempted_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    generated_system_prompt text,
    generated_welcome_message text,
    prompt_generated_at timestamp with time zone,
    prompt_error text,
    CONSTRAINT ck_campaign_contacts_status CHECK (((status)::text = ANY ((ARRAY['pending'::character varying, 'dialing'::character varying, 'completed'::character varying, 'no_answer'::character varying, 'failed'::character varying, 'do_not_call'::character varying, 'queue_timeout'::character varying])::text[])))
);
CREATE TABLE public.campaign_folders (
    id uuid NOT NULL,
    org_id uuid NOT NULL,
    created_by_id uuid,
    name character varying(255) NOT NULL,
    color character varying(20),
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    deleted_at timestamp with time zone
);
CREATE TABLE public.cloned_voices (
    id uuid NOT NULL,
    org_id uuid NOT NULL,
    created_by_id uuid,
    name character varying(255) NOT NULL,
    elevenlabs_voice_id character varying(100) NOT NULL,
    sample_file_name character varying(255) DEFAULT ''::character varying NOT NULL,
    status character varying(16) DEFAULT 'ready'::character varying NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    deleted_at timestamp with time zone,
    CONSTRAINT ck_cloned_voices_status CHECK (((status)::text = ANY ((ARRAY['ready'::character varying, 'failed'::character varying])::text[])))
);
CREATE TABLE public.do_not_call_entries (
    id uuid NOT NULL,
    org_id uuid NOT NULL,
    phone_number character varying(20) NOT NULL,
    reason character varying(32) NOT NULL,
    source_call_id uuid,
    added_by_user_id uuid,
    notes text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_do_not_call_entries_reason CHECK (((reason)::text = ANY ((ARRAY['user_request'::character varying, 'wrong_number'::character varying, 'complaint'::character varying, 'manual_block'::character varying, 'spam_report'::character varying])::text[])))
);
CREATE TABLE public.inbound_agent_templates (
    id uuid NOT NULL,
    org_id uuid NOT NULL,
    created_by_id uuid,
    name character varying(255) NOT NULL,
    description text,
    language character varying(32) DEFAULT 'hinglish'::character varying NOT NULL,
    welcome_message text DEFAULT ''::text NOT NULL,
    system_prompt text DEFAULT ''::text NOT NULL,
    voice_id character varying(100) DEFAULT 'C8R8ahkE5XosZ8qPpSPy'::character varying NOT NULL,
    voice_provider character varying(32) DEFAULT 'elevenlabs'::character varying NOT NULL,
    llm_model character varying(100) DEFAULT 'qwen/qwen3.6-27b'::character varying NOT NULL,
    llm_temperature double precision DEFAULT '0.7'::double precision NOT NULL,
    max_call_duration_seconds integer DEFAULT 600 NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    deleted_at timestamp with time zone
);
CREATE TABLE public.invoice_counters (
    year integer NOT NULL,
    last_seq integer DEFAULT 0 NOT NULL
);
CREATE SEQUENCE public.invoice_counters_year_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;
ALTER SEQUENCE public.invoice_counters_year_seq OWNED BY public.invoice_counters.year;
CREATE TABLE public.invoices (
    id uuid NOT NULL,
    org_id uuid NOT NULL,
    subscription_id uuid,
    razorpay_payment_id character varying(64) NOT NULL,
    invoice_number character varying(30) NOT NULL,
    plan_name character varying(255) NOT NULL,
    credits_per_month integer NOT NULL,
    subtotal_minor integer NOT NULL,
    cgst_minor integer DEFAULT 0 NOT NULL,
    sgst_minor integer DEFAULT 0 NOT NULL,
    igst_minor integer DEFAULT 0 NOT NULL,
    total_minor integer NOT NULL,
    currency character varying(3) DEFAULT 'INR'::character varying NOT NULL,
    customer_state character varying(100) NOT NULL,
    place_of_supply character varying(100) NOT NULL,
    storage_key character varying(500) NOT NULL,
    issued_at timestamp with time zone DEFAULT now() NOT NULL
);
CREATE TABLE public.org_company_profiles (
    id uuid NOT NULL,
    org_id uuid NOT NULL,
    company_name character varying(255) DEFAULT ''::character varying NOT NULL,
    website character varying(500),
    industry character varying(255),
    what_we_offer text,
    value_proposition text,
    target_customers text,
    key_points text,
    call_objective text,
    tone_notes text,
    extra_info text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);
CREATE TABLE public.organizations (
    id uuid NOT NULL,
    name character varying(255) NOT NULL,
    slug character varying(100) NOT NULL,
    phone character varying(20) DEFAULT ''::character varying NOT NULL,
    sip_trunk_id uuid,
    sip_caller_id character varying(20) DEFAULT ''::character varying NOT NULL,
    plan_tier character varying(50) DEFAULT 'starter'::character varying NOT NULL,
    monthly_call_quota integer DEFAULT 1000 NOT NULL,
    calls_used_this_period integer DEFAULT 0 NOT NULL,
    billing_period_start timestamp with time zone DEFAULT now() NOT NULL,
    billing_period_end timestamp with time zone DEFAULT (now() + '30 days'::interval) NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    deleted_at timestamp with time zone,
    is_active boolean DEFAULT true NOT NULL,
    credits_used_this_period integer DEFAULT 0 NOT NULL,
    last_credit_reset_at timestamp with time zone DEFAULT now() NOT NULL,
    elevenlabs_enabled boolean DEFAULT true NOT NULL,
    billing_address_line character varying(255),
    billing_city character varying(100),
    billing_state character varying(100),
    billing_pincode character varying(20),
    billing_gstin character varying(20)
);
CREATE TABLE public.plans (
    id uuid NOT NULL,
    name character varying(100) NOT NULL,
    price_minor integer NOT NULL,
    currency character varying(3) DEFAULT 'INR'::character varying NOT NULL,
    monthly_call_quota integer NOT NULL,
    max_concurrent_calls integer NOT NULL,
    features jsonb DEFAULT '{}'::jsonb NOT NULL,
    is_active boolean DEFAULT true NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    credits_per_month integer DEFAULT 500 NOT NULL,
    credit_price_cents integer DEFAULT 10 NOT NULL,
    discount_price_minor integer,
    is_custom_pricing boolean DEFAULT false NOT NULL,
    is_highlighted boolean DEFAULT false NOT NULL,
    marketing_bullets jsonb DEFAULT '[]'::jsonb NOT NULL,
    razorpay_plan_id character varying(100)
);
CREATE TABLE public.platform_admins (
    id uuid NOT NULL,
    email character varying(255) NOT NULL,
    hashed_password character varying(255) NOT NULL,
    full_name character varying(255),
    is_active boolean DEFAULT true NOT NULL,
    last_login_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);
CREATE TABLE public.platform_cost_settings (
    id integer NOT NULL,
    cost_per_minute_minor integer DEFAULT 0 NOT NULL,
    currency character varying(3) DEFAULT 'INR'::character varying NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_platform_cost_settings_singleton CHECK ((id = 1))
);
CREATE SEQUENCE public.platform_cost_settings_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;
ALTER SEQUENCE public.platform_cost_settings_id_seq OWNED BY public.platform_cost_settings.id;
CREATE TABLE public.prompt_library_entries (
    id uuid NOT NULL,
    org_id uuid NOT NULL,
    created_by_id uuid,
    source_agent_id uuid,
    title character varying(255) NOT NULL,
    tags jsonb DEFAULT '[]'::jsonb NOT NULL,
    raw_input text,
    structured_prompt text NOT NULL,
    is_high_performing boolean DEFAULT false NOT NULL,
    current_version integer DEFAULT 1 NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    deleted_at timestamp with time zone
);
CREATE TABLE public.prompt_library_versions (
    id uuid NOT NULL,
    entry_id uuid NOT NULL,
    version integer NOT NULL,
    structured_prompt text NOT NULL,
    editor_id uuid,
    note character varying(255),
    created_at timestamp with time zone DEFAULT now() NOT NULL
);
CREATE TABLE public.revenueos_clients (
    id uuid NOT NULL,
    org_id uuid NOT NULL,
    client_reference character varying(120) NOT NULL,
    user_id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);
CREATE TABLE public.revenueos_launches (
    id uuid NOT NULL,
    org_id uuid NOT NULL,
    reference character varying(120) NOT NULL,
    client_id uuid NOT NULL,
    campaign_id uuid NOT NULL,
    content_hash character varying(64) NOT NULL,
    contacts_rejected jsonb DEFAULT '[]'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);
CREATE TABLE public.sip_trunks (
    id uuid NOT NULL,
    org_id uuid NOT NULL,
    name character varying(255) NOT NULL,
    livekit_trunk_id character varying(100) NOT NULL,
    sip_domain character varying(255) NOT NULL,
    sip_username character varying(255) NOT NULL,
    sip_password text NOT NULL,
    caller_id character varying(20) NOT NULL,
    transport character varying(16) DEFAULT 'tcp'::character varying NOT NULL,
    is_default boolean DEFAULT false NOT NULL,
    is_active boolean DEFAULT true NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    deleted_at timestamp with time zone,
    vobiz_auth_id character varying(100),
    vobiz_auth_token_encrypted text,
    inbound_enabled boolean DEFAULT false NOT NULL,
    inbound_agent_template_id uuid,
    vobiz_inbound_trunk_id character varying(100),
    livekit_inbound_trunk_id character varying(100),
    livekit_inbound_dispatch_rule_id character varying(100),
    CONSTRAINT ck_sip_trunks_transport CHECK (((transport)::text = ANY ((ARRAY['tcp'::character varying, 'udp'::character varying, 'tls'::character varying])::text[])))
);
CREATE TABLE public.subscriptions (
    id uuid NOT NULL,
    org_id uuid NOT NULL,
    plan_id uuid NOT NULL,
    status character varying(20) NOT NULL,
    current_period_start timestamp with time zone,
    current_period_end timestamp with time zone,
    provider character varying(20),
    provider_customer_id character varying(255),
    provider_subscription_id character varying(255),
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    deleted_at timestamp with time zone,
    prorated_credits_override integer,
    pending_plan_id uuid,
    last_charged_payment_id character varying(255)
);
CREATE TABLE public.system_dnc_entries (
    id uuid NOT NULL,
    phone_number character varying(20) NOT NULL,
    source character varying(32) NOT NULL,
    imported_at timestamp with time zone DEFAULT now() NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_system_dnc_entries_source CHECK (((source)::text = ANY ((ARRAY['trai_ncpr'::character varying, 'manual_admin'::character varying, 'global_complaint'::character varying])::text[])))
);
CREATE TABLE public.user_sip_trunks (
    id uuid NOT NULL,
    user_id uuid NOT NULL,
    trunk_id uuid NOT NULL,
    assigned_by_id uuid,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);
CREATE TABLE public.users (
    id uuid NOT NULL,
    org_id uuid NOT NULL,
    email character varying(255) NOT NULL,
    hashed_password character varying(255) NOT NULL,
    full_name character varying(255) NOT NULL,
    role character varying(32) DEFAULT 'agent'::character varying NOT NULL,
    is_active boolean DEFAULT true NOT NULL,
    last_login_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    deleted_at timestamp with time zone,
    email_verified_at timestamp with time zone,
    CONSTRAINT ck_users_role CHECK (((role)::text = ANY ((ARRAY['admin'::character varying, 'member'::character varying, 'manager'::character varying, 'agent'::character varying])::text[])))
);
CREATE TABLE public.voice_campaigns (
    id uuid NOT NULL,
    org_id uuid NOT NULL,
    created_by_id uuid,
    name character varying(255) NOT NULL,
    description text,
    goal character varying(32) DEFAULT 'lead_generation'::character varying NOT NULL,
    agent_template_id uuid NOT NULL,
    sip_trunk_id uuid,
    status character varying(32) DEFAULT 'draft'::character varying NOT NULL,
    total_contacts integer DEFAULT 0 NOT NULL,
    completed_calls integer DEFAULT 0 NOT NULL,
    interested_count integer DEFAULT 0 NOT NULL,
    failed_count integer DEFAULT 0 NOT NULL,
    start_time timestamp with time zone,
    end_time timestamp with time zone,
    calling_window_start time without time zone DEFAULT '09:00:00'::time without time zone NOT NULL,
    calling_window_end time without time zone DEFAULT '19:00:00'::time without time zone NOT NULL,
    calling_days jsonb DEFAULT '["mon", "tue", "wed", "thu", "fri", "sat"]'::jsonb NOT NULL,
    timezone character varying(50) DEFAULT 'Asia/Kolkata'::character varying NOT NULL,
    calls_per_minute integer DEFAULT 5 NOT NULL,
    max_retries integer DEFAULT 2 NOT NULL,
    retry_after_minutes integer DEFAULT 60 NOT NULL,
    started_at timestamp with time zone,
    completed_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    deleted_at timestamp with time zone,
    folder_id uuid,
    notes text,
    is_prime boolean DEFAULT false NOT NULL,
    CONSTRAINT ck_campaigns_goal CHECK (((goal)::text = ANY ((ARRAY['lead_generation'::character varying, 'follow_up'::character varying, 'survey'::character varying, 'announcement'::character varying])::text[]))),
    CONSTRAINT ck_campaigns_status CHECK (((status)::text = ANY ((ARRAY['draft'::character varying, 'scheduled'::character varying, 'running'::character varying, 'paused'::character varying, 'completed'::character varying, 'failed'::character varying])::text[])))
);
CREATE TABLE public.voice_clone_requests (
    id uuid NOT NULL,
    org_id uuid NOT NULL,
    created_by_id uuid,
    name character varying(255) NOT NULL,
    audio_sample_key character varying(500) NOT NULL,
    audio_sample_file_name character varying(255) DEFAULT ''::character varying NOT NULL,
    audio_sample_content_type character varying(100) DEFAULT 'audio/mpeg'::character varying NOT NULL,
    consent_video_key character varying(500) NOT NULL,
    consent_video_file_name character varying(255) DEFAULT ''::character varying NOT NULL,
    consent_video_content_type character varying(100) DEFAULT 'video/webm'::character varying NOT NULL,
    status character varying(20) DEFAULT 'pending'::character varying NOT NULL,
    rejection_reason text,
    reviewed_by_admin_id uuid,
    reviewed_at timestamp with time zone,
    cloned_voice_id uuid,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_voice_clone_requests_status CHECK (((status)::text = ANY ((ARRAY['pending'::character varying, 'approved'::character varying, 'rejected'::character varying])::text[])))
);
ALTER TABLE ONLY public.invoice_counters ALTER COLUMN year SET DEFAULT nextval('public.invoice_counters_year_seq'::regclass);
ALTER TABLE ONLY public.platform_cost_settings ALTER COLUMN id SET DEFAULT nextval('public.platform_cost_settings_id_seq'::regclass);
ALTER TABLE ONLY public.agent_access_requests
    ADD CONSTRAINT agent_access_requests_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.agent_creation_requests
    ADD CONSTRAINT agent_creation_requests_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.agent_templates
    ADD CONSTRAINT agent_templates_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.alembic_version
    ADD CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num);
ALTER TABLE ONLY public.audit_log
    ADD CONSTRAINT audit_log_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.call_events
    ADD CONSTRAINT call_events_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.call_transcripts
    ADD CONSTRAINT call_transcripts_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.calls
    ADD CONSTRAINT calls_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.campaign_contacts
    ADD CONSTRAINT campaign_contacts_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.campaign_folders
    ADD CONSTRAINT campaign_folders_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.cloned_voices
    ADD CONSTRAINT cloned_voices_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.do_not_call_entries
    ADD CONSTRAINT do_not_call_entries_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.inbound_agent_templates
    ADD CONSTRAINT inbound_agent_templates_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.invoice_counters
    ADD CONSTRAINT invoice_counters_pkey PRIMARY KEY (year);
ALTER TABLE ONLY public.invoices
    ADD CONSTRAINT invoices_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.org_company_profiles
    ADD CONSTRAINT org_company_profiles_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.organizations
    ADD CONSTRAINT organizations_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.plans
    ADD CONSTRAINT plans_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.platform_admins
    ADD CONSTRAINT platform_admins_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.platform_cost_settings
    ADD CONSTRAINT platform_cost_settings_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.prompt_library_entries
    ADD CONSTRAINT prompt_library_entries_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.prompt_library_versions
    ADD CONSTRAINT prompt_library_versions_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.revenueos_clients
    ADD CONSTRAINT revenueos_clients_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.revenueos_launches
    ADD CONSTRAINT revenueos_launches_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.sip_trunks
    ADD CONSTRAINT sip_trunks_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.subscriptions
    ADD CONSTRAINT subscriptions_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.system_dnc_entries
    ADD CONSTRAINT system_dnc_entries_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.agent_access_requests
    ADD CONSTRAINT uq_agent_access_agent_user UNIQUE (agent_id, user_id);
ALTER TABLE ONLY public.call_transcripts
    ADD CONSTRAINT uq_call_transcripts_call_id UNIQUE (call_id);
ALTER TABLE ONLY public.calls
    ADD CONSTRAINT uq_calls_livekit_room_name UNIQUE (livekit_room_name);
ALTER TABLE ONLY public.do_not_call_entries
    ADD CONSTRAINT uq_dnc_org_phone UNIQUE (org_id, phone_number);
ALTER TABLE ONLY public.invoices
    ADD CONSTRAINT uq_invoices_invoice_number UNIQUE (invoice_number);
ALTER TABLE ONLY public.invoices
    ADD CONSTRAINT uq_invoices_razorpay_payment_id UNIQUE (razorpay_payment_id);
ALTER TABLE ONLY public.org_company_profiles
    ADD CONSTRAINT uq_org_company_profiles_org_id UNIQUE (org_id);
ALTER TABLE ONLY public.organizations
    ADD CONSTRAINT uq_organizations_slug UNIQUE (slug);
ALTER TABLE ONLY public.prompt_library_entries
    ADD CONSTRAINT uq_prompt_library_entries_source_agent UNIQUE (source_agent_id);
ALTER TABLE ONLY public.prompt_library_versions
    ADD CONSTRAINT uq_prompt_library_versions_entry_version UNIQUE (entry_id, version);
ALTER TABLE ONLY public.revenueos_clients
    ADD CONSTRAINT uq_revenueos_clients_client_reference UNIQUE (client_reference);
ALTER TABLE ONLY public.revenueos_clients
    ADD CONSTRAINT uq_revenueos_clients_org_id UNIQUE (org_id);
ALTER TABLE ONLY public.revenueos_launches
    ADD CONSTRAINT uq_revenueos_launches_reference UNIQUE (reference);
ALTER TABLE ONLY public.system_dnc_entries
    ADD CONSTRAINT uq_system_dnc_entries_phone_number UNIQUE (phone_number);
ALTER TABLE ONLY public.user_sip_trunks
    ADD CONSTRAINT uq_user_sip_trunks UNIQUE (user_id, trunk_id);
ALTER TABLE ONLY public.users
    ADD CONSTRAINT uq_users_email UNIQUE (email);
ALTER TABLE ONLY public.user_sip_trunks
    ADD CONSTRAINT user_sip_trunks_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.voice_campaigns
    ADD CONSTRAINT voice_campaigns_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.voice_clone_requests
    ADD CONSTRAINT voice_clone_requests_pkey PRIMARY KEY (id);
CREATE INDEX ix_agent_access_agent_id ON public.agent_access_requests USING btree (agent_id);
CREATE INDEX ix_agent_access_user_id ON public.agent_access_requests USING btree (user_id);
CREATE INDEX ix_agent_creation_requests_org_id ON public.agent_creation_requests USING btree (org_id);
CREATE INDEX ix_agent_creation_requests_user_id ON public.agent_creation_requests USING btree (user_id);
CREATE INDEX ix_agent_templates_created_by_id ON public.agent_templates USING btree (created_by_id);
CREATE INDEX ix_agent_templates_deleted_at ON public.agent_templates USING btree (deleted_at);
CREATE INDEX ix_agent_templates_org_id ON public.agent_templates USING btree (org_id);
CREATE INDEX ix_audit_log_created_at ON public.audit_log USING btree (created_at);
CREATE INDEX ix_audit_log_org_id ON public.audit_log USING btree (org_id);
CREATE INDEX ix_call_campaign_id ON public.calls USING btree (campaign_id);
CREATE INDEX ix_call_events_call_id ON public.call_events USING btree (call_id);
CREATE INDEX ix_call_org_created ON public.calls USING btree (org_id, created_at);
CREATE INDEX ix_call_phone_number ON public.calls USING btree (phone_number);
CREATE INDEX ix_call_started_at ON public.calls USING btree (started_at);
CREATE INDEX ix_call_transcripts_full_text_gin ON public.call_transcripts USING gin (to_tsvector('english'::regconfig, COALESCE(full_text, ''::text)));
CREATE INDEX ix_calls_campaign_id ON public.calls USING btree (campaign_id);
CREATE INDEX ix_calls_campaign_outcome ON public.calls USING btree (campaign_id, outcome);
CREATE INDEX ix_calls_contact_id ON public.calls USING btree (contact_id);
CREATE UNIQUE INDEX ix_calls_livekit_room_name ON public.calls USING btree (livekit_room_name);
CREATE INDEX ix_calls_org_id ON public.calls USING btree (org_id);
CREATE INDEX ix_calls_org_started_at ON public.calls USING btree (org_id, started_at);
CREATE INDEX ix_calls_outcome ON public.calls USING btree (outcome);
CREATE INDEX ix_calls_phone_number ON public.calls USING btree (phone_number);
CREATE INDEX ix_calls_sip_trunk_id ON public.calls USING btree (sip_trunk_id);
CREATE INDEX ix_calls_status ON public.calls USING btree (status);
CREATE INDEX ix_campaign_contact_campaign_created ON public.campaign_contacts USING btree (campaign_id, created_at);
CREATE INDEX ix_campaign_contact_campaign_status ON public.campaign_contacts USING btree (campaign_id, status);
CREATE INDEX ix_campaign_contacts_campaign_id ON public.campaign_contacts USING btree (campaign_id);
CREATE INDEX ix_campaign_contacts_campaign_status ON public.campaign_contacts USING btree (campaign_id, status);
CREATE INDEX ix_campaign_contacts_org_phone ON public.campaign_contacts USING btree (org_id, phone);
CREATE INDEX ix_campaign_contacts_status ON public.campaign_contacts USING btree (status);
CREATE INDEX ix_campaign_folders_deleted_at ON public.campaign_folders USING btree (deleted_at);
CREATE INDEX ix_campaign_folders_org_id ON public.campaign_folders USING btree (org_id);
CREATE INDEX ix_campaigns_agent_template_id ON public.voice_campaigns USING btree (agent_template_id);
CREATE INDEX ix_campaigns_created_by_id ON public.voice_campaigns USING btree (created_by_id);
CREATE INDEX ix_campaigns_deleted_at ON public.voice_campaigns USING btree (deleted_at);
CREATE INDEX ix_campaigns_folder_id ON public.voice_campaigns USING btree (folder_id);
CREATE INDEX ix_campaigns_org_id ON public.voice_campaigns USING btree (org_id);
CREATE INDEX ix_campaigns_org_status ON public.voice_campaigns USING btree (org_id, status);
CREATE INDEX ix_campaigns_sip_trunk_id ON public.voice_campaigns USING btree (sip_trunk_id);
CREATE INDEX ix_campaigns_status ON public.voice_campaigns USING btree (status);
CREATE INDEX ix_cloned_voices_created_by_id ON public.cloned_voices USING btree (created_by_id);
CREATE INDEX ix_cloned_voices_deleted_at ON public.cloned_voices USING btree (deleted_at);
CREATE INDEX ix_cloned_voices_elevenlabs_voice_id ON public.cloned_voices USING btree (elevenlabs_voice_id);
CREATE INDEX ix_cloned_voices_org_id ON public.cloned_voices USING btree (org_id);
CREATE INDEX ix_do_not_call_entries_org_id ON public.do_not_call_entries USING btree (org_id);
CREATE INDEX ix_do_not_call_entries_phone_number ON public.do_not_call_entries USING btree (phone_number);
CREATE INDEX ix_do_not_call_entries_source_call_id ON public.do_not_call_entries USING btree (source_call_id);
CREATE INDEX ix_inbound_agent_templates_created_by_id ON public.inbound_agent_templates USING btree (created_by_id);
CREATE INDEX ix_inbound_agent_templates_deleted_at ON public.inbound_agent_templates USING btree (deleted_at);
CREATE INDEX ix_inbound_agent_templates_org_id ON public.inbound_agent_templates USING btree (org_id);
CREATE INDEX ix_invoices_org_id ON public.invoices USING btree (org_id);
CREATE INDEX ix_org_company_profiles_org_id ON public.org_company_profiles USING btree (org_id);
CREATE INDEX ix_organizations_deleted_at ON public.organizations USING btree (deleted_at);
CREATE INDEX ix_organizations_sip_trunk_id ON public.organizations USING btree (sip_trunk_id);
CREATE UNIQUE INDEX ix_organizations_slug ON public.organizations USING btree (slug);
CREATE UNIQUE INDEX ix_platform_admins_email ON public.platform_admins USING btree (email);
CREATE INDEX ix_prompt_library_entries_created_by_id ON public.prompt_library_entries USING btree (created_by_id);
CREATE INDEX ix_prompt_library_entries_deleted_at ON public.prompt_library_entries USING btree (deleted_at);
CREATE INDEX ix_prompt_library_entries_org_id ON public.prompt_library_entries USING btree (org_id);
CREATE INDEX ix_prompt_library_entries_source_agent_id ON public.prompt_library_entries USING btree (source_agent_id);
CREATE INDEX ix_prompt_library_entries_tags_gin ON public.prompt_library_entries USING gin (tags);
CREATE INDEX ix_prompt_library_versions_entry_id ON public.prompt_library_versions USING btree (entry_id);
CREATE INDEX ix_revenueos_clients_org_id ON public.revenueos_clients USING btree (org_id);
CREATE INDEX ix_revenueos_launches_campaign_id ON public.revenueos_launches USING btree (campaign_id);
CREATE INDEX ix_revenueos_launches_client_id ON public.revenueos_launches USING btree (client_id);
CREATE INDEX ix_revenueos_launches_org_id ON public.revenueos_launches USING btree (org_id);
CREATE INDEX ix_sip_trunks_deleted_at ON public.sip_trunks USING btree (deleted_at);
CREATE INDEX ix_sip_trunks_org_id ON public.sip_trunks USING btree (org_id);
CREATE INDEX ix_subscriptions_deleted_at ON public.subscriptions USING btree (deleted_at);
CREATE UNIQUE INDEX ix_subscriptions_org_id_active_unique ON public.subscriptions USING btree (org_id) WHERE (deleted_at IS NULL);
CREATE INDEX ix_subscriptions_plan_id ON public.subscriptions USING btree (plan_id);
CREATE UNIQUE INDEX ix_system_dnc_entries_phone_number ON public.system_dnc_entries USING btree (phone_number);
CREATE INDEX ix_user_sip_trunks_trunk_id ON public.user_sip_trunks USING btree (trunk_id);
CREATE INDEX ix_user_sip_trunks_user_id ON public.user_sip_trunks USING btree (user_id);
CREATE INDEX ix_users_deleted_at ON public.users USING btree (deleted_at);
CREATE UNIQUE INDEX ix_users_email ON public.users USING btree (email);
CREATE INDEX ix_users_org_id ON public.users USING btree (org_id);
CREATE INDEX ix_voice_clone_requests_created_by_id ON public.voice_clone_requests USING btree (created_by_id);
CREATE INDEX ix_voice_clone_requests_org_id ON public.voice_clone_requests USING btree (org_id);
CREATE INDEX ix_voice_clone_requests_status ON public.voice_clone_requests USING btree (status);
ALTER TABLE ONLY public.agent_access_requests
    ADD CONSTRAINT agent_access_requests_agent_id_fkey FOREIGN KEY (agent_id) REFERENCES public.agent_templates(id) ON DELETE CASCADE;
ALTER TABLE ONLY public.agent_access_requests
    ADD CONSTRAINT agent_access_requests_org_id_fkey FOREIGN KEY (org_id) REFERENCES public.organizations(id) ON DELETE CASCADE;
ALTER TABLE ONLY public.agent_access_requests
    ADD CONSTRAINT agent_access_requests_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;
ALTER TABLE ONLY public.agent_creation_requests
    ADD CONSTRAINT agent_creation_requests_org_id_fkey FOREIGN KEY (org_id) REFERENCES public.organizations(id) ON DELETE CASCADE;
ALTER TABLE ONLY public.agent_creation_requests
    ADD CONSTRAINT agent_creation_requests_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;
ALTER TABLE ONLY public.agent_templates
    ADD CONSTRAINT agent_templates_created_by_id_fkey FOREIGN KEY (created_by_id) REFERENCES public.users(id) ON DELETE SET NULL;
ALTER TABLE ONLY public.agent_templates
    ADD CONSTRAINT agent_templates_org_id_fkey FOREIGN KEY (org_id) REFERENCES public.organizations(id) ON DELETE CASCADE;
ALTER TABLE ONLY public.call_events
    ADD CONSTRAINT call_events_call_id_fkey FOREIGN KEY (call_id) REFERENCES public.calls(id) ON DELETE CASCADE;
ALTER TABLE ONLY public.call_transcripts
    ADD CONSTRAINT call_transcripts_call_id_fkey FOREIGN KEY (call_id) REFERENCES public.calls(id) ON DELETE CASCADE;
ALTER TABLE ONLY public.calls
    ADD CONSTRAINT calls_campaign_id_fkey FOREIGN KEY (campaign_id) REFERENCES public.voice_campaigns(id) ON DELETE SET NULL;
ALTER TABLE ONLY public.calls
    ADD CONSTRAINT calls_contact_id_fkey FOREIGN KEY (contact_id) REFERENCES public.campaign_contacts(id) ON DELETE SET NULL;
ALTER TABLE ONLY public.calls
    ADD CONSTRAINT calls_org_id_fkey FOREIGN KEY (org_id) REFERENCES public.organizations(id) ON DELETE RESTRICT;
ALTER TABLE ONLY public.campaign_contacts
    ADD CONSTRAINT campaign_contacts_campaign_id_fkey FOREIGN KEY (campaign_id) REFERENCES public.voice_campaigns(id) ON DELETE CASCADE;
ALTER TABLE ONLY public.campaign_contacts
    ADD CONSTRAINT campaign_contacts_org_id_fkey FOREIGN KEY (org_id) REFERENCES public.organizations(id) ON DELETE CASCADE;
ALTER TABLE ONLY public.campaign_folders
    ADD CONSTRAINT campaign_folders_created_by_id_fkey FOREIGN KEY (created_by_id) REFERENCES public.users(id) ON DELETE SET NULL;
ALTER TABLE ONLY public.campaign_folders
    ADD CONSTRAINT campaign_folders_org_id_fkey FOREIGN KEY (org_id) REFERENCES public.organizations(id) ON DELETE CASCADE;
ALTER TABLE ONLY public.voice_campaigns
    ADD CONSTRAINT campaigns_agent_template_id_fkey FOREIGN KEY (agent_template_id) REFERENCES public.agent_templates(id) ON DELETE RESTRICT;
ALTER TABLE ONLY public.voice_campaigns
    ADD CONSTRAINT campaigns_created_by_id_fkey FOREIGN KEY (created_by_id) REFERENCES public.users(id) ON DELETE SET NULL;
ALTER TABLE ONLY public.voice_campaigns
    ADD CONSTRAINT campaigns_folder_id_fkey FOREIGN KEY (folder_id) REFERENCES public.campaign_folders(id) ON DELETE SET NULL;
ALTER TABLE ONLY public.voice_campaigns
    ADD CONSTRAINT campaigns_org_id_fkey FOREIGN KEY (org_id) REFERENCES public.organizations(id) ON DELETE CASCADE;
ALTER TABLE ONLY public.voice_campaigns
    ADD CONSTRAINT campaigns_sip_trunk_id_fkey FOREIGN KEY (sip_trunk_id) REFERENCES public.sip_trunks(id) ON DELETE SET NULL;
ALTER TABLE ONLY public.cloned_voices
    ADD CONSTRAINT cloned_voices_created_by_id_fkey FOREIGN KEY (created_by_id) REFERENCES public.users(id) ON DELETE SET NULL;
ALTER TABLE ONLY public.cloned_voices
    ADD CONSTRAINT cloned_voices_org_id_fkey FOREIGN KEY (org_id) REFERENCES public.organizations(id) ON DELETE CASCADE;
ALTER TABLE ONLY public.do_not_call_entries
    ADD CONSTRAINT do_not_call_entries_added_by_user_id_fkey FOREIGN KEY (added_by_user_id) REFERENCES public.users(id) ON DELETE SET NULL;
ALTER TABLE ONLY public.do_not_call_entries
    ADD CONSTRAINT do_not_call_entries_org_id_fkey FOREIGN KEY (org_id) REFERENCES public.organizations(id) ON DELETE CASCADE;
ALTER TABLE ONLY public.do_not_call_entries
    ADD CONSTRAINT do_not_call_entries_source_call_id_fkey FOREIGN KEY (source_call_id) REFERENCES public.calls(id) ON DELETE SET NULL;
ALTER TABLE ONLY public.calls
    ADD CONSTRAINT fk_calls_sip_trunk_id FOREIGN KEY (sip_trunk_id) REFERENCES public.sip_trunks(id) ON DELETE SET NULL;
ALTER TABLE ONLY public.organizations
    ADD CONSTRAINT fk_organizations_default_sip_trunk FOREIGN KEY (sip_trunk_id) REFERENCES public.sip_trunks(id) ON DELETE SET NULL;
ALTER TABLE ONLY public.sip_trunks
    ADD CONSTRAINT fk_sip_trunks_inbound_agent_template_id FOREIGN KEY (inbound_agent_template_id) REFERENCES public.inbound_agent_templates(id) ON DELETE SET NULL;
ALTER TABLE ONLY public.subscriptions
    ADD CONSTRAINT fk_subscriptions_pending_plan_id_plans FOREIGN KEY (pending_plan_id) REFERENCES public.plans(id) ON DELETE SET NULL;
ALTER TABLE ONLY public.inbound_agent_templates
    ADD CONSTRAINT inbound_agent_templates_created_by_id_fkey FOREIGN KEY (created_by_id) REFERENCES public.users(id) ON DELETE SET NULL;
ALTER TABLE ONLY public.inbound_agent_templates
    ADD CONSTRAINT inbound_agent_templates_org_id_fkey FOREIGN KEY (org_id) REFERENCES public.organizations(id) ON DELETE CASCADE;
ALTER TABLE ONLY public.invoices
    ADD CONSTRAINT invoices_org_id_fkey FOREIGN KEY (org_id) REFERENCES public.organizations(id) ON DELETE CASCADE;
ALTER TABLE ONLY public.invoices
    ADD CONSTRAINT invoices_subscription_id_fkey FOREIGN KEY (subscription_id) REFERENCES public.subscriptions(id) ON DELETE SET NULL;
ALTER TABLE ONLY public.org_company_profiles
    ADD CONSTRAINT org_company_profiles_org_id_fkey FOREIGN KEY (org_id) REFERENCES public.organizations(id) ON DELETE CASCADE;
ALTER TABLE ONLY public.prompt_library_entries
    ADD CONSTRAINT prompt_library_entries_created_by_id_fkey FOREIGN KEY (created_by_id) REFERENCES public.users(id) ON DELETE SET NULL;
ALTER TABLE ONLY public.prompt_library_entries
    ADD CONSTRAINT prompt_library_entries_org_id_fkey FOREIGN KEY (org_id) REFERENCES public.organizations(id) ON DELETE CASCADE;
ALTER TABLE ONLY public.prompt_library_entries
    ADD CONSTRAINT prompt_library_entries_source_agent_id_fkey FOREIGN KEY (source_agent_id) REFERENCES public.agent_templates(id) ON DELETE SET NULL;
ALTER TABLE ONLY public.prompt_library_versions
    ADD CONSTRAINT prompt_library_versions_editor_id_fkey FOREIGN KEY (editor_id) REFERENCES public.users(id) ON DELETE SET NULL;
ALTER TABLE ONLY public.prompt_library_versions
    ADD CONSTRAINT prompt_library_versions_entry_id_fkey FOREIGN KEY (entry_id) REFERENCES public.prompt_library_entries(id) ON DELETE CASCADE;
ALTER TABLE ONLY public.revenueos_clients
    ADD CONSTRAINT revenueos_clients_org_id_fkey FOREIGN KEY (org_id) REFERENCES public.organizations(id) ON DELETE CASCADE;
ALTER TABLE ONLY public.revenueos_clients
    ADD CONSTRAINT revenueos_clients_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;
ALTER TABLE ONLY public.revenueos_launches
    ADD CONSTRAINT revenueos_launches_campaign_id_fkey FOREIGN KEY (campaign_id) REFERENCES public.voice_campaigns(id) ON DELETE CASCADE;
ALTER TABLE ONLY public.revenueos_launches
    ADD CONSTRAINT revenueos_launches_client_id_fkey FOREIGN KEY (client_id) REFERENCES public.revenueos_clients(id) ON DELETE CASCADE;
ALTER TABLE ONLY public.revenueos_launches
    ADD CONSTRAINT revenueos_launches_org_id_fkey FOREIGN KEY (org_id) REFERENCES public.organizations(id) ON DELETE CASCADE;
ALTER TABLE ONLY public.sip_trunks
    ADD CONSTRAINT sip_trunks_org_id_fkey FOREIGN KEY (org_id) REFERENCES public.organizations(id) ON DELETE CASCADE;
ALTER TABLE ONLY public.subscriptions
    ADD CONSTRAINT subscriptions_org_id_fkey FOREIGN KEY (org_id) REFERENCES public.organizations(id) ON DELETE CASCADE;
ALTER TABLE ONLY public.subscriptions
    ADD CONSTRAINT subscriptions_plan_id_fkey FOREIGN KEY (plan_id) REFERENCES public.plans(id) ON DELETE RESTRICT;
ALTER TABLE ONLY public.user_sip_trunks
    ADD CONSTRAINT user_sip_trunks_assigned_by_id_fkey FOREIGN KEY (assigned_by_id) REFERENCES public.users(id) ON DELETE SET NULL;
ALTER TABLE ONLY public.user_sip_trunks
    ADD CONSTRAINT user_sip_trunks_trunk_id_fkey FOREIGN KEY (trunk_id) REFERENCES public.sip_trunks(id) ON DELETE CASCADE;
ALTER TABLE ONLY public.user_sip_trunks
    ADD CONSTRAINT user_sip_trunks_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;
ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_org_id_fkey FOREIGN KEY (org_id) REFERENCES public.organizations(id) ON DELETE CASCADE;
ALTER TABLE ONLY public.voice_clone_requests
    ADD CONSTRAINT voice_clone_requests_cloned_voice_id_fkey FOREIGN KEY (cloned_voice_id) REFERENCES public.cloned_voices(id) ON DELETE SET NULL;
ALTER TABLE ONLY public.voice_clone_requests
    ADD CONSTRAINT voice_clone_requests_created_by_id_fkey FOREIGN KEY (created_by_id) REFERENCES public.users(id) ON DELETE SET NULL;
ALTER TABLE ONLY public.voice_clone_requests
    ADD CONSTRAINT voice_clone_requests_org_id_fkey FOREIGN KEY (org_id) REFERENCES public.organizations(id) ON DELETE CASCADE;
ALTER TABLE ONLY public.voice_clone_requests
    ADD CONSTRAINT voice_clone_requests_reviewed_by_admin_id_fkey FOREIGN KEY (reviewed_by_admin_id) REFERENCES public.platform_admins(id) ON DELETE SET NULL;
ALTER TABLE public.agent_access_requests ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.agent_creation_requests ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.alembic_version ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.audit_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.campaign_folders ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.cloned_voices ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.inbound_agent_templates ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.invoice_counters ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.invoices ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.org_company_profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.plans ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.platform_admins ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.platform_cost_settings ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.prompt_library_entries ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.prompt_library_versions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.revenueos_clients ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.revenueos_launches ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.subscriptions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.user_sip_trunks ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.voice_clone_requests ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.agent_templates ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.call_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.call_transcripts ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.calls ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.campaign_contacts ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.do_not_call_entries ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.organizations ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.sip_trunks ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.system_dnc_entries ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.users ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.voice_campaigns ENABLE ROW LEVEL SECURITY;
INSERT INTO public.alembic_version (version_num) VALUES ('0040');
INSERT INTO public.platform_cost_settings (id, cost_per_minute_minor, currency) VALUES (1, 0, 'INR');
COMMIT;
